from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import closet, selfit_outfit_match as matching, styling_catalog, storage
from app.auth import get_current_user
from app.main import app
from app.selfit_studio import StudioOutfit, save_studio_outfit


@pytest.fixture(autouse=True)
def no_default_wardrobe_items(monkeypatch):
    monkeypatch.setattr(closet, '_with_default_items', lambda data: data)
    monkeypatch.delenv('SELFIT_OUTFIT_MATCH_PROVIDER', raising=False)


@pytest.fixture
def notes(monkeypatch):
    looks = styling_catalog.delivery_looks()
    monkeypatch.setattr(matching, '_anchor_image', lambda anchor: Image.new('RGB', (32, 32)))
    monkeypatch.setattr(styling_catalog, '_asset_url', lambda ref: '/static/' + ref['assetId'] + '.png')
    return looks


def choose(monkeypatch, slot='top', candidate_index=-1):
    calls = []
    def answer(image, prompt, schema):
        calls.append(prompt)
        if len(calls) % 2:
            return {'slot': slot, 'description': '白色短袖，廓形简洁宽松，适合与利落下装搭配。'}
        candidates=json.loads(prompt.split('\n',1)[1])['candidates']
        candidate=candidates[candidate_index]
        return {'no_match': False, 'matches': [{
            'candidate_id': candidate['candidate_id'],
            'replace_item_id': candidate['replaceable_items'][0]['item_id'],
            'reason': '白色短袖能延续套装的清爽配色，与保留的下装和鞋包形成协调的日常组合。'}]}
    monkeypatch.setattr(matching, 'ask_vision', answer)
    return calls


def anchor():
    return {'item_id':'owned-shirt', 'title':'我的白 T', 'category':'top', 'assets':{'cutout_path':'/user-assets/closet/owned.png'}, 'source':{'type':'upload'}}


def test_ai_reads_all_eligible_descriptions_and_replaces_exactly_one(notes, monkeypatch):
    before=deepcopy(notes)
    calls=choose(monkeypatch)
    result=matching.match_notebook_outfit(anchor())
    data=json.loads(calls[1].split('\n',1)[1])
    eligible=[look for look in notes if any(matching.notebook_slot(item)=='top' for item in look['items'])]
    assert len(data['candidates'])==len(eligible)>1
    assert [x['outfit_description'] for x in data['candidates']]==[x['outfit_description'] for x in eligible]
    source=styling_catalog.adapt_outfit(eligible[-1])
    row=result['outfits'][0]
    old_id=result['matches'][0]['replaced_item_id']
    assert row['item_ids']==['owned-shirt' if key==old_id else key for key in source['item_ids']]
    assert next(x for x in row['items'] if x['item_id']=='owned-shirt')['assets']==anchor()['assets']
    for item in row['items']:
        if item['item_id']=='owned-shirt': continue
        original=next(x for x in source['items'] if x['item_id']==item['item_id'])
        assert item['assets']==original['assets']
        assert item['wearing_instruction']==original['wearing_instruction']
        assert old_id not in item['styling']['paired_with_item_ids']
    assert result['mode']=='ai_notebook_match'
    assert notes==before


def test_accessory_kinds_and_layer_roles_do_not_cross(notes, monkeypatch):
    for slot in ['necklace','earrings','bracelet','glasses','outer']:
        calls=choose(monkeypatch,slot)
        result=matching.match_notebook_outfit(anchor())
        candidates=json.loads(calls[1].split('\n',1)[1])['candidates']
        for candidate in candidates:
            allowed={x['item_id'] for x in candidate['replaceable_items']}
            assert all(x['slot']==slot for x in candidate['items'] if x['item_id'] in allowed)
        assert 'owned-shirt' in result['outfits'][0]['item_ids']


@pytest.mark.parametrize('decision',[
    {'no_match': False, 'matches': [{'candidate_id': 'invented', 'replace_item_id': 'anything', 'reason': '匹配'}]},
    {'no_match': False, 'matches': [{'candidate_id': 'C1', 'replace_item_id': {}, 'reason': '匹配'}]},
    {'no_match': False, 'matches': [{'candidate_id': 'C1', 'replace_item_id': 'not-in-this-note', 'reason': '匹配'}]},
    {'no_match': False, 'matches': [{'candidate_id': [], 'replace_item_id': 'anything', 'reason': '匹配'}]},
    {'no_match': False, 'matches': []},
    {'no_match': False},
    {'no_match': True, 'matches': []},
])
def test_rejects_invalid_or_unsuitable_ai_result(notes,monkeypatch,decision):
    responses=iter([{'slot':'top','description':'白 T'},decision])
    monkeypatch.setattr(matching,'ask_vision',lambda *args:next(responses))
    with pytest.raises(HTTPException) as error: matching.match_notebook_outfit(anchor())
    assert error.value.status_code in (422,502)


def test_no_corresponding_slot_does_not_call_ranking(notes,monkeypatch):
    monkeypatch.setattr(matching,'delivery_looks',lambda:[notes[0]])
    calls=choose(monkeypatch,'brooch')
    with pytest.raises(HTTPException) as error: matching.match_notebook_outfit(anchor())
    assert error.value.status_code==422 and len(calls)==1


def test_same_tryon_provider_is_reused_and_no_fake_success(monkeypatch):
    from app import tryon
    monkeypatch.setattr(tryon,'_has_runway_google_provider',lambda:True)
    monkeypatch.setattr(closet.AIGarmentCutoutProvider,'_analyze_inventory_with_runway',lambda *args:'{"slot":"top"}')
    monkeypatch.setattr(closet.AIGarmentCutoutProvider,'_analyze_inventory_with_openai',lambda *args:pytest.fail('wrong provider'))
    assert matching.ask_vision(Image.new('RGB',(1,1)),'prompt')=={'slot':'top'}
    monkeypatch.setattr(tryon,'_has_runway_google_provider',lambda:False)
    monkeypatch.setattr(tryon,'_has_openai_compatible_provider',lambda:False)
    with pytest.raises(HTTPException) as error: matching.ask_vision(Image.new('RGB',(1,1)),'prompt')
    assert error.value.status_code==503


def test_authenticated_preview_does_not_save_and_cannot_use_another_users_item(notes,monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    choose(monkeypatch)
    with storage.user_storage('owner'):
        manifest=closet._ensure_manifest();manifest['items'].append(anchor());closet._write_manifest(manifest)
    client=TestClient(app)
    assert client.post('/selfit/try-on/items/owned-shirt/outfits').status_code==401
    app.dependency_overrides[get_current_user]=lambda:{'user_id':'owner'}
    try:
        response=client.post('/selfit/try-on/items/owned-shirt/outfits')
        assert response.status_code==200
        with storage.user_storage('owner'):
            assert len(closet._ensure_manifest()['items'])==1
            assert closet._ensure_outfit_manifest()['outfits']==[]
        app.dependency_overrides[get_current_user]=lambda:{'user_id':'someone-else'}
        assert client.post('/selfit/try-on/items/owned-shirt/outfits').status_code==404
    finally: app.dependency_overrides.pop(get_current_user,None)


def test_saved_notebook_match_keeps_every_piece_and_material_paths_for_tryon(notes,monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    look=next(x for x in notes if len(x['items'])>8 and any(matching.notebook_slot(i)=='top' for i in x['items']))
    monkeypatch.setattr(matching,'delivery_looks',lambda:[look])
    choose(monkeypatch)
    result=matching.match_notebook_outfit(anchor())
    monkeypatch.setattr(closet,'_published_catalog_outfits',lambda **kw:[])
    monkeypatch.setattr(styling_catalog,'delivery_looks',lambda:[look])
    image=tmp_path/'image.png';Image.new('RGB',(120,160),'white').save(image)
    monkeypatch.setattr('app.material_assets.material_image_path',lambda asset_id:image)
    with storage.user_storage('save-owner'):
        own=anchor();own['assets']['cutout_path']=str(image)
        manifest=closet._ensure_manifest();manifest['items'].append(own);closet._write_manifest(manifest)
        ids=result['outfits'][0]['item_ids']
        layout=[{'id':key,'x':(i%4)*24,'y':(i//4)*24,'w':22,'h':22} for i,key in enumerate(ids)]
        payload=StudioOutfit(item_ids=ids,favorite=True,canvas_layout=layout)
        saved=save_studio_outfit(payload)
        assert len(saved['item_ids'])==len(look['items'])>8
        assert set(saved['display_item_ids'])==set(ids)
        assert saved['overflow_items']==[]
        plan,loaded=closet.outfit_as_tryon_plan(saved['outfit_id'])
        assert [item['item_id'] for item in plan['items']]==saved['item_ids']
        assert loaded['favorite'] is True
        assert save_studio_outfit(payload)['outfit_id']==saved['outfit_id']
        for item in plan['items']:
            assert Path(item['image_path']).exists()
            if item['item_id']!='owned-shirt': assert item['wearing_instruction']
    with storage.user_storage('someone-else'):
        with pytest.raises(HTTPException): closet.get_outfit(saved['outfit_id'])


def test_default_white_tee_uses_fixture_matches_without_model_calls(notes, monkeypatch):
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixture path must not call the model'))
    tee = {**anchor(), 'item_id': '6cfcffd0a4c66d10', 'title': '白 T', 'is_default': True}
    result = matching.match_notebook_outfit(tee)
    assert result['mode'] == 'fixture_notebook_match'
    assert result['anchor_item_id'] == '6cfcffd0a4c66d10'
    assert result['persona_group'] is None
    assert len(result['outfits']) == len(result['matches']) == 3
    for outfit, note in zip(result['outfits'], result['matches']):
        assert '6cfcffd0a4c66d10' in outfit['item_ids']
        assert note['replaced_item_id'] not in outfit['item_ids']
        assert note['reason'] and note['image_url'] and note['title']
    titles = [note['title'] for note in result['matches']]
    assert len(set(titles)) == 3


def _tee():
    return {**anchor(), 'item_id': '6cfcffd0a4c66d10', 'title': '白 T', 'is_default': True}


def _top_pick(look):
    return next(item for item in look['items'] if matching.notebook_slot(item) == 'top')


def test_male_white_tee_data_has_five_ordered_triples():
    data = matching._load_curated_white_tee()
    male = data['male']
    assert set(male['persona_groups']) == {'ease', 'edge', 'mute', 'wabi'}
    assert set(male['library_groups']) == {'standard'}
    assert all(set(versions) == {'standard'} for versions in male['persona_groups'].values())
    looks = {l['look_id']: l for l in matching.delivery_looks()}
    assert male['candidate_pool_size'] == len([l for l in looks.values() if l['note_binding'].get('gender') == 'male']) == 16
    assert male['candidate_pool_sizes'] == {'standard': 16}
    groups = [versions['standard'] for versions in male['persona_groups'].values()]
    groups += list(male['library_groups'].values())
    assert len(groups) == 5
    for group in groups:
        assert group['gender'] == 'male' and group['body_profile'] == 'standard'
        assert group['no_match'] is False
        assert len(group['matches']) == len({m['candidate_id'] for m in group['matches']}) == 3
        for pick in group['matches']:
            look = looks[pick['candidate_id']]
            assert look['note_binding']['gender'] == 'male'
            assert look['note_binding']['bodyProfile'] == 'standard'
            item = next(i for i in look['items'] if i['item_id'] == pick['replace_item_id'])
            assert matching.notebook_slot(item) == 'top'
            assert 80 <= len(pick['reason']) <= 140
    # With two T-shirts, replace only the inner white tee, retaining the blue one.
    blue = next(m for m in male['persona_groups']['edge']['standard']['matches']
                if looks[m['candidate_id']]['note_binding']['noteId'] == 'outfits-04')
    replaced = next(i for i in looks[blue['candidate_id']]['items'] if i['item_id'] == blue['replace_item_id'])
    assert replaced['garment_name'] == '白色打底短袖T恤'


@pytest.mark.parametrize('persona', ['ease', 'edge', 'mute', 'wabi', None, 'film'])
def test_male_white_tee_uses_exact_saved_compositions_without_ai(notes, monkeypatch, persona):
    male = matching._load_curated_white_tee()['male']
    expected = male['persona_groups'].get(persona, {}).get('standard') or male['library_groups']['standard']
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: persona)
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixed matches must not call AI'))
    before = deepcopy(notes)
    result = matching.match_notebook_outfit(_tee(), user_id='male-owner', gender='male')
    assert result['gender'] == 'male' and result['body_profile'] == 'standard'
    assert len(result['matches']) == len(result['outfits']) == 3
    assert result['persona_group'] == expected.get('persona')
    by_id = {look['look_id']: look for look in notes}
    for pick, note, outfit in zip(expected['matches'], result['matches'], result['outfits']):
        original = styling_catalog.adapt_outfit(by_id[pick['candidate_id']])
        assert note['source_outfit_id'] == original['outfit_id']
        assert note['reason'] == pick['reason']
        assert outfit['item_ids'] == [_tee()['item_id'] if key == note['replaced_item_id'] else key for key in original['item_ids']]
        tee = next(i for i in outfit['items'] if i['item_id'] == _tee()['item_id'])
        assert tee['assets'] == _tee()['assets']
        assert 'styling' not in tee, 'old garment details must not be attached to the white T'
        for item in outfit['items']:
            if item['item_id'] == _tee()['item_id']:
                continue
            source = next(i for i in original['items'] if i['item_id'] == item['item_id'])
            assert item['assets'] == source['assets']
            assert item['wearing_instruction'] == source['wearing_instruction']
            assert note['replaced_item_id'] not in item['styling']['paired_with_item_ids']
    assert notes == before


def test_male_white_tee_backfills_only_male_library(notes, monkeypatch):
    data = matching._load_curated_white_tee()
    male = data['male']
    chosen = male['persona_groups']['edge']['standard']['matches']
    first = deepcopy(chosen[0])
    chosen[1] = deepcopy(data['library_groups']['standard']['matches'][0])
    chosen[2]['candidate_id'] = 'missing'
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: data)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'edge')
    result = matching.match_notebook_outfit(_tee(), gender='male')
    expected = [first] + male['library_groups']['standard']['matches'][:2]
    assert [m['reason'] for m in result['matches']] == [m['reason'] for m in expected]
    assert all('-male_' in m['source_outfit_id'] for m in result['matches'])


@pytest.mark.parametrize('gender', ['female', 'male'])
def test_cross_gender_library_references_are_rejected(notes, monkeypatch, gender):
    data = matching._load_curated_white_tee()
    selected, other = (data['male'], data) if gender == 'male' else (data, data['male'])
    selected['library_groups']['standard']['matches'][0] = deepcopy(other['library_groups']['standard']['matches'][0])
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: data)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: None)
    with pytest.raises(HTTPException) as error:
        matching.match_notebook_outfit(_tee(), gender=gender)
    assert error.value.status_code == 503


def test_male_catalog_missing_or_unsupported_body_never_falls_back_to_female(notes, monkeypatch):
    with pytest.raises(HTTPException) as error:
        matching.match_notebook_outfit(_tee(), gender='male', body_profile='curvy')
    assert error.value.status_code == 422 and '男生微胖版' in error.value.detail
    data = matching._load_curated_white_tee()
    data.pop('male')
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: data)
    with pytest.raises(HTTPException) as error:
        matching.match_notebook_outfit(_tee(), gender='male')
    assert error.value.status_code == 503


def test_white_tee_api_gender_comes_from_current_account(notes, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'ease')
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixed matches must not call AI'))
    with storage.user_storage('tee-gender-owner'):
        manifest = closet._ensure_manifest()
        manifest['items'].append(_tee())
        closet._write_manifest(manifest)
    user = {'user_id': 'tee-gender-owner', 'gender': 'male'}
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        path = '/selfit/try-on/items/6cfcffd0a4c66d10/outfits'
        response = client.post(path + '?gender=female', json={'gender': 'female'})
        assert response.status_code == 200
        assert response.json()['gender'] == 'male'
        assert all('-male_' in m['source_outfit_id'] for m in response.json()['matches'])
        assert client.post(path + '?body_profile=curvy').status_code == 422
        user['gender'] = 'female'
        response = client.post(path + '?gender=male')
        assert response.status_code == 200 and response.json()['gender'] == 'female'
        assert all('-male_' not in m['source_outfit_id'] for m in response.json()['matches'])
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _curated(looks):
    data = json.loads(matching.CURATED_WHITE_TEE_PATH.read_text())
    data['persona_groups'] = {'film': {'standard': {
        'persona': 'FILM_虚焦胶片型人格', 'body_profile': 'standard', 'matches': [
            {'candidate_id': look['look_id'], 'replace_item_id': _top_pick(look)['item_id'],
             'reason': f'人格定制理由{index}，说明白 T 与这套保留单品的色彩比例衔接。'}
            for index, look in enumerate(looks)]}}}
    return data


def test_default_white_tee_prefers_curated_persona_group(notes, monkeypatch):
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixture path must not call the model'))
    picks = [look for look in notes if any(matching.notebook_slot(i) == 'top' for i in look['items'])][:3]
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: _curated(picks))
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'film')
    result = matching.match_notebook_outfit(_tee(), user_id='u1')
    assert result['persona_group'] == 'FILM_虚焦胶片型人格'
    assert [note['title'] for note in result['matches']] == [look['note_binding']['name'] for look in picks]
    assert [note['reason'] for note in result['matches']] == [f'人格定制理由{i}，说明白 T 与这套保留单品的色彩比例衔接。' for i in range(3)]


def test_default_white_tee_backfills_library_when_curated_group_is_incomplete(notes, monkeypatch):
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixture path must not call the model'))
    pick = next(look for look in notes if any(matching.notebook_slot(i) == 'top' for i in look['items']))
    data = _curated([pick])
    data['persona_groups']['film']['standard']['matches'].append(
        {'candidate_id': 'GONE_不存在_outfits_99_失效', 'replace_item_id': 'x', 'reason': '失效引用会被跳过。'})
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: data)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'film')
    result = matching.match_notebook_outfit(_tee(), user_id='u1')
    assert len(result['matches']) == 3
    assert result['matches'][0]['title'] == pick['note_binding']['name']
    assert result['matches'][0]['reason'].startswith('人格定制理由')
    expected = [m for m in data['library_groups']['standard']['matches']
                if m['candidate_id'] != pick['look_id']][:2]
    assert [note['reason'] for note in result['matches'][1:]] == [m['reason'] for m in expected]


def test_default_white_tee_unknown_persona_uses_library_backfill(notes, monkeypatch):
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('fixture path must not call the model'))
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: None)
    result = matching.match_notebook_outfit(_tee(), user_id='u1')
    assert result['persona_group'] is None
    assert len(result['matches']) == 3
    saved = matching._load_curated_white_tee()['library_groups']['standard']['matches']
    assert [note['reason'] for note in result['matches']] == [m['reason'] for m in saved]


def test_white_tee_data_has_exactly_three_real_distinct_top_replacements_per_group():
    from app.recommendation_profile import PERSONAS

    data = matching._load_curated_white_tee()
    assert set(data['persona_groups']) == PERSONAS
    assert {code for code, groups in data['persona_groups'].items() if 'curvy' in groups} == {'film', 'loop', 'void', 'wabi'}
    assert all('standard' in groups for groups in data['persona_groups'].values())
    assert set(data['library_groups']) == {'standard', 'curvy'}
    looks = matching.delivery_looks() + matching.inspiration_looks()
    # These picks were curated before the separate male delivery was supplied.
    assert data['candidate_pool_size'] == len([look for look in looks if look['note_binding'].get('gender') != 'male']) == 96
    assert data['candidate_pool_sizes'] == {'standard': 80, 'curvy': 16}
    by_id = {look['look_id']: look for look in looks}
    groups = [group for versions in data['persona_groups'].values() for group in versions.values()]
    groups += list(data['library_groups'].values())
    assert len(groups) == 22
    for group in groups:
        assert group['no_match'] is False
        assert len(group['matches']) == data['matches_per_group'] == matching.MAX_MATCHES == 3
        assert len({m['candidate_id'] for m in group['matches']}) == 3
        for match in group['matches']:
            look = by_id[match['candidate_id']]
            assert look['note_binding'].get('bodyProfile', 'standard') == group['body_profile']
            replaced = next(i for i in look['items'] if i['item_id'] == match['replace_item_id'])
            assert matching.notebook_slot(replaced) == 'top'
            assert match['reason'].strip()


def test_all_saved_white_tee_groups_produce_the_exact_three_compositions(notes, monkeypatch):
    data = matching._load_curated_white_tee()
    by_id = {look['look_id']: look for look in matching.delivery_looks() + matching.inspiration_looks()}
    monkeypatch.setattr(matching, 'ask_vision', lambda *args: pytest.fail('saved groups must not call the model'))
    groups = [(code, body, group) for code, versions in data['persona_groups'].items() for body, group in versions.items()]
    groups += [(None, body, group) for body, group in data['library_groups'].items()]
    for code, body, group in groups:
        monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: code)
        result = matching.match_notebook_outfit(_tee(), user_id='u1', body_profile=body)
        assert result['body_profile'] == body
        assert len(result['outfits']) == len(result['matches']) == 3
        for picked, note, outfit in zip(group['matches'], result['matches'], result['outfits']):
            original = styling_catalog.adapt_outfit(by_id[picked['candidate_id']])
            assert note['source_outfit_id'] == original['outfit_id']
            assert note['reason'] == picked['reason']
            assert outfit['item_ids'] == [_tee()['item_id'] if key == note['replaced_item_id'] else key for key in original['item_ids']]


def test_missing_curvy_persona_uses_saved_curvy_library_not_standard(notes, monkeypatch):
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'bolt')
    result = matching.match_notebook_outfit(_tee(), user_id='u1', body_profile='curvy')
    saved = matching._load_curated_white_tee()['library_groups']['curvy']['matches']
    assert result['persona_group'] is None
    assert result['body_profile'] == 'curvy'
    assert [m['reason'] for m in result['matches']] == [m['reason'] for m in saved]


@pytest.mark.parametrize('invalid', ['missing_look', 'wrong_slot', 'wrong_body', 'duplicate'])
def test_incomplete_saved_library_does_not_return_two_or_choose_unrecorded_looks(notes, monkeypatch, invalid):
    data = matching._load_curated_white_tee()
    picks = data['library_groups']['standard']['matches']
    if invalid == 'missing_look':
        picks[0]['candidate_id'] = 'missing'
    elif invalid == 'wrong_slot':
        look = next(l for l in notes if l['look_id'] == picks[0]['candidate_id'])
        picks[0]['replace_item_id'] = next(i['item_id'] for i in look['items'] if matching.notebook_slot(i) != 'top')
    elif invalid == 'wrong_body':
        picks[0] = data['library_groups']['curvy']['matches'][0]
    else:
        picks[0] = picks[1]
    monkeypatch.setattr(matching, '_load_curated_white_tee', lambda: data)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: None)
    with pytest.raises(HTTPException) as error:
        matching.match_notebook_outfit(_tee())
    assert error.value.status_code == 503


def test_white_tee_body_profile_is_available_to_authenticated_api(notes, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(matching, '_user_persona_key', lambda user_id: 'film')
    with storage.user_storage('white-tee-owner'):
        manifest = closet._ensure_manifest()
        manifest['items'].append(_tee())
        closet._write_manifest(manifest)
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'white-tee-owner'}
    try:
        client = TestClient(app)
        path = '/selfit/try-on/items/6cfcffd0a4c66d10/outfits'
        standard = client.post(path)
        curvy = client.post(path + '?body_profile=curvy')
        assert standard.status_code == curvy.status_code == 200
        assert standard.json()['body_profile'] == 'standard'
        assert curvy.json()['body_profile'] == 'curvy'
        assert len(curvy.json()['matches']) == 3
        assert standard.json()['matches'] != curvy.json()['matches']
        assert client.post(path + '?body_profile=unknown').status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_ai_returns_up_to_three_ranked_matches(notes, monkeypatch):
    monkeypatch.setattr(matching, '_anchor_image', lambda anchor: Image.new('RGB', (32, 32)))
    monkeypatch.setattr(styling_catalog, '_asset_url', lambda ref: '/static/' + ref['assetId'] + '.png')
    captured = []
    def answer(image, prompt, schema):
        captured.append(prompt)
        if len(captured) == 1:
            return {'slot': 'top', 'description': '白色短袖。'}
        candidates = json.loads(prompt.split('\n', 1)[1])['candidates']
        picks = candidates[:3]
        return {'no_match': False, 'matches': [
            {'candidate_id': c['candidate_id'], 'replace_item_id': c['replaceable_items'][0]['item_id'],
             'reason': f'第{i + 1}套与白 T 的配色和比例协调。'} for i, c in enumerate(picks)]}
    monkeypatch.setattr(matching, 'ask_vision', answer)
    result = matching.match_notebook_outfit(anchor())
    assert result['mode'] == 'ai_notebook_match'
    assert len(result['outfits']) == len(result['matches']) == 3
    for outfit, note in zip(result['outfits'], result['matches']):
        assert 'owned-shirt' in outfit['item_ids']
        assert note['replaced_item_id'] not in outfit['item_ids']
        assert note['candidate_count'] >= 3
    assert len({note['source_outfit_id'] for note in result['matches']}) == 3


def test_duplicate_or_extra_ai_matches_are_deduplicated_and_capped(notes, monkeypatch):
    monkeypatch.setattr(matching, '_anchor_image', lambda anchor: Image.new('RGB', (32, 32)))
    monkeypatch.setattr(styling_catalog, '_asset_url', lambda ref: '/static/' + ref['assetId'] + '.png')
    captured = []
    def answer(image, prompt, schema):
        captured.append(prompt)
        if len(captured) == 1:
            return {'slot': 'top', 'description': '白色短袖。'}
        candidates = json.loads(prompt.split('\n', 1)[1])['candidates']
        picks = [candidates[0], candidates[0], *candidates[1:5]]
        return {'no_match': False, 'matches': [
            {'candidate_id': c['candidate_id'], 'replace_item_id': c['replaceable_items'][0]['item_id'],
             'reason': '这套与用户单品的色彩衔接自然。'} for c in picks]}
    monkeypatch.setattr(matching, 'ask_vision', answer)
    result = matching.match_notebook_outfit(anchor())
    assert len(result['outfits']) == len(result['matches']) == 3
    assert len({note['source_outfit_id'] for note in result['matches']}) == 3

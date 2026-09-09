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
        return {'candidate_id':candidate['candidate_id'], 'replace_item_id':candidate['replaceable_items'][0]['item_id'],
                'reason':'白色短袖能延续套装的清爽配色，与保留的下装和鞋包形成协调的日常组合。'}
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
    old_id=result['match']['replaced_item_id']
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
    {'candidate_id':'invented','replace_item_id':'anything','reason':'匹配'},
    {'candidate_id':'C1','replace_item_id':{},'reason':'匹配'},
    {'candidate_id':'C1','replace_item_id':'not-in-this-note','reason':'匹配'},
    {'candidate_id':[],'replace_item_id':'anything','reason':'匹配'},
    {'no_match':True},
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

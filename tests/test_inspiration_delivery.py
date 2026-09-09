import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import closet, inspiration_catalog, selfit_studio, storage, styling_catalog, tryon
from app.auth import get_current_user
from app.material_assets import MaterialRegistry


def test_sixteen_inspiration_looks_keep_all_103_items_and_do_not_change_personas():
    data = inspiration_catalog.inspiration_delivery()
    assert len(styling_catalog.delivery_looks()) == 80
    assert [topic['id'] for topic in data['topics']] == ['commute', 'date', 'vacation', 'trend']
    assert len(data['looks']) == 16
    ids = set()
    source = json.loads(Path('app/data/inspiration-source-assets.v1.json').read_text())['files']
    for look in data['looks']:
        outfit = closet.get_outfit(styling_catalog.outfit_id(look))
        assert outfit['primary_persona'] is None
        assert outfit['item_ids'] == outfit['layer_sequence_inner_to_outer']
        assert len(outfit['items']) == len(look['items'])
        assert set(outfit['item_ids']).isdisjoint(ids)
        ids.update(outfit['item_ids'])
        assert len(outfit['item_ids']) == len(set(outfit['item_ids']))
        for raw in look['items']:
            ref = raw['image_asset']
            relative = str(Path(look['source_path']).parent / raw['asset_filename'])
            assert ref['sourceAssetId'] == source[relative]['assetId']
            assert MaterialRegistry().get(ref['assetId'])['storage']['provider'] == 'qiniu'
            assert raw['cutout']['rgbUnchanged'] is True
    assert len(ids) == 103


def test_topics_require_auth_but_no_personality_test_and_fail_closed(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(selfit_studio.router)
    client = TestClient(app)
    url = '/selfit/try-on/inspiration-topics'
    assert client.get(url).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'visitor'}
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 96
    assert len(data['topics']) == 20
    scene_topics, persona_topics = data['topics'][:4], data['topics'][4:]
    assert [len(topic['outfits']) for topic in scene_topics] == [4] * 4
    assert sum(len(outfit['items']) for topic in scene_topics for outfit in topic['outfits']) == 103
    from app.selfit_report import _personality_template_catalog
    templates = _personality_template_catalog()['types']
    assert [topic['persona'] for topic in persona_topics] == list(templates)
    expected = {styling_catalog.outfit_id(look): look for look in styling_catalog.delivery_looks()}
    actual = [outfit['outfit_id'] for topic in persona_topics for outfit in topic['outfits']]
    assert len(actual) == len(set(actual)) == 80
    assert set(actual) == set(expected), 'keep every delivered audience variant, exactly once'
    for topic in persona_topics:
        code = topic['persona']
        assert topic['id'] == f'persona-{code}'
        assert topic['title'] == templates[code]['metadata']['name']
        assert topic['cover'] == topic['outfits'][0]['cover_path']
        assert topic['previews'] == [outfit['cover_path'] for outfit in topic['outfits'][1:4]]
        assert [outfit['body_profile'] for outfit in topic['outfits'][:4]] == ['standard'] * 4
        for outfit in topic['outfits']:
            binding = expected[outfit['outfit_id']]['note_binding']
            assert outfit['primary_persona'] == binding['persona'] == code
            assert outfit['body_profile'] == binding['bodyProfile']
            assert outfit['item_ids'] == outfit['layer_sequence_inner_to_outer']
    broken = tmp_path / 'delivery.json'
    payload = inspiration_catalog.inspiration_delivery()
    payload['uploadStatus'] = 'pending'
    broken.write_text(json.dumps(payload))
    monkeypatch.setattr(inspiration_catalog, 'DELIVERY_PATH', broken)
    assert client.get(url).status_code == 503


def test_scene_outfit_plan_uses_original_photo_and_every_cutout(monkeypatch, tmp_path):
    look = next(look for look in inspiration_catalog.inspiration_looks() if len(look['items']) == 9)
    paths = {}
    def material_path(asset_id):
        path = tmp_path / (asset_id + '.png')
        if not path.exists():
            Image.new('RGBA', (80, 120), (150, 90, 60, 255)).save(path)
        paths[asset_id] = path
        return path
    monkeypatch.setattr(styling_catalog, 'material_image_path', material_path)
    plan, outfit = closet.outfit_as_tryon_plan(styling_catalog.outfit_id(look))
    assert Path(plan['style_reference']['image_path']) == paths[look['source_asset']['assetId']]
    assert len(plan['items']) == 9
    assert plan['layer_sequence_inner_to_outer'] == outfit['item_ids']
    assert {item['image_id'] for item in plan['items']} == {item['image_asset']['assetId'] for item in look['items']}
    context = tryon._build_outfit_prompt_context(tryon._normalize_outfit_tryon_plan(plan))
    assert len(context['items']) == 9
    assert all(item['styling']['closure_state'] for item in context['items'])
    assert all('cutout' not in item['styling'] for item in context['items'])
    with pytest.raises(HTTPException) as error:
        closet.get_outfit('report_inspiration_commute_outfits-01_stale')
    assert error.value.status_code == 404


def test_saving_scene_outfit_is_idempotent_and_user_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    look = inspiration_catalog.inspiration_looks()[0]
    outfit = styling_catalog.adapt_outfit(look)
    monkeypatch.setattr(closet, '_published_catalog_outfits', lambda **_: [])
    def layout(oid, items, *_):
        path = tmp_path / 'cover.png'
        Image.new('RGB', (40, 60), 'white').save(path)
        return {'path': path, 'layout_version': 'test', 'layout_mode': 'test', 'canvas': {},
                'layout_slots': [], 'display_item_ids': [i['item_id'] for i in items],
                'overflow_items': [], 'warnings': []}
    monkeypatch.setattr(closet, '_build_outfit_cover', layout)
    app = FastAPI()
    app.include_router(selfit_studio.router)
    user = {'user_id': 'alice'}
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    body = {'item_ids': outfit['item_ids'], 'title': outfit['title'], 'favorite': True}
    endpoint = '/selfit/try-on/outfits'
    before = client.get('/selfit/try-on/wardrobe').json()
    assert not before['outfits']
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    assert client.post(endpoint, json=body).json()['outfit_id'] == first.json()['outfit_id']
    saved = client.get('/selfit/try-on/wardrobe').json()
    assert len(saved['outfits']) == 1
    assert saved['outfits'][0]['item_ids'] == outfit['item_ids']
    assert not any(i['item_id'] in outfit['item_ids'] for i in saved['items']), 'saving an outfit does not imply owning its pieces'
    user['user_id'] = 'bob'
    assert not client.get('/selfit/try-on/wardrobe').json()['outfits']

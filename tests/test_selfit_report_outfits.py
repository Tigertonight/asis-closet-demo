import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import closet, styling_catalog as styling, selfit_report_outfits as report, tryon
from app.auth import get_current_user
from app.material_assets import MaterialRegistry
from app.selfit_report import _personality_template_catalog


def test_all_96_delivered_notes_keep_exact_assets_items_and_layers(monkeypatch):
    # Verify the delivery contract independently of upload completion.
    monkeypatch.setattr(MaterialRegistry, 'get', lambda _, asset_id: {'url': '/static/fixture.png'})
    catalog = _personality_template_catalog()
    templates = {**catalog['types'], **catalog['variants']}
    all_ids = set()
    total = 0
    for key, template in templates.items():
        result = report.report_outfits(template['typeId'], ['outfits-04', 'outfits-01', 'outfits-03', 'outfits-02'], key)
        assert result['mode'] == 'live'
        assert [x['report_note']['id'].split(':')[-1] for x in result['outfits']] == ['outfits-04', 'outfits-01', 'outfits-03', 'outfits-02']
        for outfit in result['outfits']:
            assert outfit['source'] == 'styling_delivery'
            assert outfit['outfit_id'] not in all_ids
            all_ids.add(outfit['outfit_id'])
            assert outfit['item_ids'] == outfit['layer_sequence_inner_to_outer'] == [i['item_id'] for i in outfit['items']]
            assert outfit['cover_path'] == outfit['report_note']['image_url']
            assert all(i['assets']['cutout_path'].startswith('/api/v1/material-assets/') for i in outfit['items'])
            assert all(i['styling']['wearing_method'] == i['wearing_instruction'] for i in outfit['items'])
            assert closet.get_outfit(outfit['outfit_id']) == {k:v for k,v in outfit.items() if k != 'report_note'}
            total += len(outfit['items'])
    assert len(all_ids) == 96 and total == 569


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(MaterialRegistry, 'get', lambda _, asset_id: {'url': '/static/fixture.png'})
    app = FastAPI()
    app.include_router(report.router)
    client = TestClient(app)
    assert client.get('/selfit/try-on/report-outfits?persona=void&note_ids=outfits-01').status_code == 401
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'report-reader'}
    return client


def test_subset_validation_variant_and_stale_photo(client):
    endpoint = '/selfit/try-on/report-outfits'
    response = client.get(endpoint, params={'persona': 'VOID', 'note_ids': 'outfits-02,outfits-01'})
    assert response.status_code == 200
    assert [o['report_note']['title'] for o in response.json()['outfits']] == ['舒服就行', '躺平朋克']
    for ids, expected in [('outfits-01,outfits-01', 422), ('x', 404), ('1,2,3,4,5', 422)]:
        assert client.get(endpoint, params={'persona': 'void', 'note_ids': ids}).status_code == expected
    assert client.get(endpoint, params={'persona':'void','template_id':'film-curvy','note_ids':'outfits-01'}).status_code == 404
    curvy = client.get(endpoint, params={'persona':'void','template_id':'void-curvy','note_ids':'outfits-01'}).json()
    assert curvy['outfits'][0]['outfit_id'] != response.json()['outfits'][1]['outfit_id']
    query = {'persona':'void','note_ids':'outfits-01','note_assets':'legacy'}
    legacy = client.get(endpoint, params=query)
    assert legacy.status_code == 200
    assert legacy.json()['resolved_legacy_assets'] is True
    assert legacy.json()['outfits'][0]['source_asset_id'] == response.json()['outfits'][1]['source_asset_id']
    query['note_assets'] = 'asset_' + '0' * 64
    assert client.get(endpoint, params=query).status_code == 409
    query['note_assets'] = response.json()['outfits'][1]['source_asset_id']
    assert client.get(endpoint, params=query).status_code == 200
    query['note_assets'] += ',extra'
    assert client.get(endpoint, params=query).status_code == 422


def test_legacy_four_notes_and_mixed_asset_versions(client):
    endpoint = '/selfit/try-on/report-outfits'
    query = {'persona': 'void', 'template_id': 'void',
             'note_ids': 'outfits-01,outfits-02,outfits-03,outfits-04',
             'note_assets': 'legacy,legacy,legacy,legacy'}
    response = client.get(endpoint, params=query)
    assert response.status_code == 200
    body = response.json()
    assert body['mode'] == 'live' and body['resolved_legacy_assets'] is True
    assets = [o['report_note']['image_asset_id'] for o in body['outfits']]
    assert len(assets) == 4 and all(a.startswith('asset_') for a in assets)
    query['note_assets'] = ','.join(assets)
    assert client.get(endpoint, params=query).json()['resolved_legacy_assets'] is False
    query['note_assets'] = ','.join(['legacy', *assets[1:]])
    assert client.get(endpoint, params=query).status_code == 200
    query['note_assets'] = ','.join(['legacy', assets[0], *assets[2:]])
    assert client.get(endpoint, params=query).status_code == 409, 'legacy must not disable checks for concrete IDs'
    query.update(template_id='void-curvy', note_assets='legacy,legacy,legacy,legacy')
    curvy = client.get(endpoint, params=query)
    assert curvy.status_code == 200
    assert all(o['template_id'] == 'void-curvy' for o in curvy.json()['outfits'])
    assert curvy.json()['outfits'][0]['source_asset_id'] != assets[0]


def test_backend_report_card_exposes_compatible_asset_ids():
    from app.selfit_report import _template_card
    asset_id = 'asset_' + 'a' * 64
    card = _template_card({'id':'outfits-01', 'image':{'assetId':asset_id, 'src':'https://cdn.example.com/look.jpg'}})
    assert card['assetId'] == card['imageAssetId'] == asset_id


def test_home_random_notes_have_four_unique_photos_and_real_outfits(client, monkeypatch):
    endpoint = '/selfit/try-on/report-outfits/random'
    monkeypatch.setattr(report.random, 'sample', lambda rows, count: rows[:count])
    response = client.get(endpoint)
    assert response.status_code == 200
    rows = response.json()['outfits']
    assert len(rows) == len({o['outfit_id'] for o in rows}) == len({o['source_asset_id'] for o in rows}) == 4
    for row in rows:
        assert row['cover_path'] == row['report_note']['image_url']
        assert row['title'] == row['report_note']['title']
        resolved = closet.get_outfit(row['outfit_id'])
        assert row['items'] == resolved['items']
        assert row['item_ids'] == row['layer_sequence_inner_to_outer']
    monkeypatch.setattr(report.random, 'sample', lambda rows, count: rows[-count:])
    refreshed = client.get(endpoint).json()['outfits']
    assert {o['outfit_id'] for o in refreshed} != {o['outfit_id'] for o in rows}
    chosen = rows[2]
    pinned = client.get(endpoint, params={'selected_outfit_id': chosen['outfit_id']}).json()['outfits']
    assert pinned[0] == chosen
    assert len(pinned) == len({o['source_asset_id'] for o in pinned}) == 4
    assert len(client.get(endpoint, params={'selected_outfit_id': 'outfit_bolt_master_01'}).json()['outfits']) == 4


def test_home_notes_require_auth_and_fail_without_delivery(monkeypatch):
    app = FastAPI()
    app.include_router(report.router)
    client = TestClient(app)
    endpoint = '/selfit/try-on/report-outfits/random'
    assert client.get(endpoint).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'visitor'}
    monkeypatch.setattr(report, 'delivery_looks', lambda: [])
    response = client.get(endpoint)
    assert response.status_code == 503
    assert response.json()['detail'] == '穿搭笔记暂时无法加载，请稍后重试。'


def test_missing_data_or_asset_never_substitutes_mock(monkeypatch, client):
    endpoint = '/selfit/try-on/report-outfits?persona=void&note_ids=outfits-01'
    original = styling.delivery_looks()
    monkeypatch.setattr(report, 'delivery_looks', lambda: [])
    assert client.get(endpoint).status_code == 503
    monkeypatch.setattr(report, 'delivery_looks', lambda: original)
    def missing(*_): raise KeyError('unregistered')
    monkeypatch.setattr(MaterialRegistry, 'get', missing)
    assert client.get(endpoint).status_code == 503
    with pytest.raises(HTTPException) as error:
        closet.get_outfit('report_void_outfits-01_obsolete')
    assert error.value.status_code == 404


def test_real_plan_preserves_14_items_and_styling(monkeypatch, tmp_path):
    look = next(x for x in styling.delivery_looks() if len(x['items']) == 14)
    monkeypatch.setattr(MaterialRegistry, 'get', lambda _, asset_id: {'url':'/static/fixture.png'})
    image_path = tmp_path / 'fixture.png'
    Image.new('RGB', (80, 120), 'pink').save(image_path)
    monkeypatch.setattr(styling, 'material_image_path', lambda _: image_path)
    plan, outfit = closet.outfit_as_tryon_plan(styling.outfit_id(look))
    normalized = tryon._normalize_outfit_tryon_plan(plan)
    context = tryon._build_outfit_prompt_context(normalized)
    assert len(normalized['items']) == len(context['items']) == 14
    assert plan['layer_sequence_inner_to_outer'] == outfit['item_ids']
    assert all(i['styling']['closure_state'] for i in context['items'])
    pasted = []
    original_paste = tryon._paste_board_image
    def capture(canvas, path, box):
        pasted.append(box)
        original_paste(canvas, path, box)
    monkeypatch.setattr(tryon, '_paste_board_image', capture)
    board = tryon._build_outfit_reference_board(normalized, tmp_path / 'board.png')
    assert len(pasted) == 15 and len(set(pasted)) == 15, 'every item gets a separate cell plus the source photo'
    with Image.open(board) as image:
        assert all(0 <= b[0] < b[2] <= image.width and 0 <= b[1] < b[3] <= image.height for b in pasted)


def test_local_material_hash_and_missing_file(monkeypatch, tmp_path):
    import app.material_assets as materials
    monkeypatch.setattr(materials, 'ROOT', tmp_path)
    path = tmp_path / 'app/static/item.png'
    path.parent.mkdir(parents=True)
    Image.new('RGB', (40, 40), 'pink').save(path)
    record = {'url': '/static/item.png?v=1', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    monkeypatch.setattr(MaterialRegistry, 'get', lambda *_: record)
    assert styling.material_image_path('fixture') == path
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'): styling.material_image_path('fixture')
    path.unlink()
    with pytest.raises(ValueError, match='Missing'): styling.material_image_path('fixture')

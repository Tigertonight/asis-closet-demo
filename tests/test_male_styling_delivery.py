import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app import inspiration_catalog, selfit_report_outfits, styling_catalog
from app.auth import get_current_user
from app.material_assets import MaterialRegistry, asset_content_url
from app.selfit_report import _personality_template_catalog
from scripts.import_selfit_report_data import build_runtime
from scripts.register_male_styling_delivery import source_looks
from scripts.register_material_assets import register_catalog_images

CODES = {'ease', 'edge', 'mute', 'wabi'}


def test_male_delivery_keeps_sixteen_exact_looks_and_all_101_items():
    looks = [look for look in styling_catalog.delivery_looks() if look['note_binding'].get('gender') == 'male']
    assert len(looks) == 16 and sum(len(look['items']) for look in looks) == 101
    assert {look['note_binding']['persona'] for look in looks} == CODES
    sources = json.loads(Path('app/data/styling-source-assets.v1.json').read_text())['files']
    cutouts = json.loads(Path('app/data/styling-cutout-assets.v1.json').read_text())['files']
    templates = _personality_template_catalog()['variants']
    ids = set()
    for look in looks:
        binding = look['note_binding']
        assert binding['templateId'] == binding['persona'] + '-male'
        assert binding['bodyProfile'] == 'standard'
        note = templates[binding['templateId']]['recommendations']['outfits']['items'][binding['position'] - 1]
        assert note['sourceUrl'] == binding['sourceUrl'] and note['byline'] == binding['byline']
        assert binding['noteLinkStatus'] == ('provided_by_user' if binding['sourceUrl'] else 'not_provided')
        assert note['name'] == binding['name'] and note['image']['assetId'] == look['source_asset']['assetId']
        assert look['outfit_description']
        ordered = sorted(look['items'], key=lambda item: item['layer_order'])
        assert look['layer_sequence_inner_to_outer'] == [item['item_id'] for item in ordered]
        for item in look['items']:
            assert item['item_id'] not in ids
            ids.add(item['item_id'])
            assert item['description'] and item['cutout']['rgbUnchanged'] and item['cutout']['visualReview'] == 'accepted'
            ref = item['image_asset']
            relative = (Path(look['source_path']).parent / item['asset_filename']).as_posix()
            assert sources[relative]['assetId'] == ref['sourceAssetId']
            assert cutouts[relative]['assetId'] == ref['assetId']
            assert MaterialRegistry().get(ref['assetId'])['storage']['provider'] == 'qiniu'


@pytest.mark.parametrize('code', sorted(CODES))
def test_male_report_notes_are_distinct_and_stale_female_assets_are_rejected(code):
    app = FastAPI(); app.include_router(selfit_report_outfits.router)
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'male-delivery-test', 'gender': 'male'}
    client = TestClient(app); endpoint = '/selfit/try-on/report-outfits'
    params = {'persona': code, 'template_id': code + '-male', 'note_ids': 'outfits-01,outfits-02,outfits-03,outfits-04'}
    male = client.get(endpoint, params=params)
    assert male.status_code == 200
    rows = male.json()['outfits']
    assert len(rows) == 4 and all(row['gender'] == 'male' for row in rows)
    standard = selfit_report_outfits.report_outfits(code, ['outfits-01'])['outfits'][0]
    assert standard['outfit_id'] != rows[0]['outfit_id'] and standard['source_asset_id'] != rows[0]['source_asset_id']
    params.update(note_ids='outfits-01', note_assets=standard['source_asset_id'])
    assert client.get(endpoint, params=params).status_code == 409
    params.update(note_assets=rows[0]['source_asset_id'])
    assert client.get(endpoint, params=params).status_code == 200
    params['persona'] = 'film'
    assert client.get(endpoint, params=params).status_code == 404


def test_home_gender_sampling_and_inspiration_keep_existing_covers():
    app = FastAPI(); app.include_router(selfit_report_outfits.router)
    user = {'user_id': 'male-delivery-test', 'gender': 'male'}
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app); endpoint = '/selfit/try-on/report-outfits/random'
    rows = client.get(endpoint).json()['outfits']
    assert len(rows) == 4 and all(row['gender'] == 'male' for row in rows)
    user['gender'] = 'female'
    female = client.get(endpoint).json()['outfits']
    assert len(female) == 4 and all(row['gender'] != 'male' for row in female)
    pinned = client.get(endpoint, params={'selected_outfit_id': rows[0]['outfit_id']}).json()['outfits']
    assert pinned[0] == rows[0] and all(row['gender'] != 'male' for row in pinned[1:])
    topics = {topic['id']: topic for topic in inspiration_catalog.inspiration_topics()['topics']}
    for code in CODES:
        topic = topics['persona-' + code]
        assert [outfit['template_id'] for outfit in topic['outfits'][:4]] == [code] * 4
        assert len([outfit for outfit in topic['outfits'] if outfit['gender'] == 'male']) == 4


def test_import_preserves_registered_asset_id_without_reuploading_api_route(tmp_path):
    path = tmp_path / 'tiny.png'; Image.new('RGB', (4, 6), 'red').save(path)
    registry = MaterialRegistry(tmp_path / 'registry.json')
    aid = registry.register(path.read_bytes(), 'https://example.test/source.png', 'image/png')
    template = {'code': 'EASE', 'name': '松弛讲究-男', 'gender': 'male', 'hero': asset_content_url(aid), 'outfits': [
        {'name': '真实素材', 'assetId': aid, 'image': asset_content_url(aid), 'imageWidth': 4, 'imageHeight': 6}]}
    built = register_catalog_images(build_runtime({'templates': [template]}, {}), registry)
    image = built['variants']['ease-male']['recommendations']['outfits']['items'][0]['image']
    assert image['assetId'] == aid and image['width'] == 4 and image['height'] == 6
    assert 'src' not in image
    hero = built['variants']['ease-male']['hero']['image']
    assert hero['assetId'] == aid and 'src' not in hero


def test_source_import_rejects_missing_pairing_and_escaped_image(tmp_path):
    source = tmp_path / 'source/4男 拆款'; descriptions = {}
    for code in sorted(CODES):
        folder = code.upper() + '_测试-男_male'
        for pos in range(1, 5):
            parent = source / folder / f'{folder}-{pos}-示例-拆款'; parent.mkdir(parents=True)
            image = source / '穿搭原图' / folder / f'outfits_{pos:02d}_示例.jpg'; image.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (4, 6), 'red').save(image)
            Image.new('RGB', (4, 6), 'blue').save(parent / 'top.png')
            item_id = f'{code}-{pos}'
            data = {'look_id': item_id, 'source_image': image.name, 'items': [{'item_id': item_id, 'asset_filename': 'top.png', 'category': '上装内搭', 'layer_order': 0}],
                    'source_outfit_item_ids': [item_id], 'layer_sequence_inner_to_outer': [item_id]}
            (parent / 'styling.json').write_text(json.dumps(data))
            descriptions[f'{code}-{pos:02d}'] = {'outfit_description': '示例穿搭', 'items': ['示例上衣']}
    (tmp_path / 'descriptions.json').write_text(json.dumps(descriptions))
    (tmp_path / 'source-package.json').write_text(json.dumps({'sha256': 'a' * 64}))
    assert len(source_looks(tmp_path)) == 16
    original = copy.deepcopy(data)
    data['items'][0]['paired_with_item_ids'] = ['nonexistent']
    (parent / 'styling.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Unresolved item pairing'): source_looks(tmp_path)
    original['items'][0]['asset_filename'] = '../outside.png'
    (parent / 'styling.json').write_text(json.dumps(original))
    with pytest.raises(ValueError, match='basename'): source_looks(tmp_path)

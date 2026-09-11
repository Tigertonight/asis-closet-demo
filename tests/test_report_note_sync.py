import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.material_assets import (
    IMAGE_ID_FIELDS, MaterialRegistry, asset_content_url, material_source_url,
    resolve_image_references,
)
from app.report_template_identity import template_identity
from scripts.import_selfit_report_data import build_pool, build_runtime
from scripts.upload_content_pool import OssUploadClient

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / 'app/static/report-builder/data/16-personality-templates.json'
RUNTIME = ROOT / 'app/static/selfit/data/personality-report-templates.v1.json'


@pytest.mark.parametrize('code', ['FILM', 'WABI', 'LOOP', 'VOID'])
def test_curvy_identity_repairs_export_conflict(code):
    item = {'code': code, 'templateId': f'{code.lower()}-curvy', 'bodyProfile': 'standard'}
    assert template_identity(item) == (code.lower(), 'curvy', 'unisex', f'{code.lower()}-curvy')


def test_runtime_keeps_curvy_separate_and_rejects_duplicate_audiences():
    master = json.loads(MASTER.read_text())
    prior = json.loads(RUNTIME.read_text())
    result = build_runtime(master, prior)
    assert len(result['types']) == 16
    assert set(result['variants']) == {'film-curvy', 'wabi-curvy', 'void-curvy', 'loop-curvy',
                                       'ease-male', 'edge-male', 'mute-male', 'wabi-male'}
    assert result['types']['film']['recommendations']['outfits']['items'][0]['name'] == '牛仔工装'
    assert result['variants']['film-curvy']['recommendations']['outfits']['items'][0]['name'] == '胶片carhartt'
    master['templates'].append(copy.deepcopy(master['templates'][0]))
    with pytest.raises(ValueError, match='Duplicate report audience'):
        build_runtime(master, prior)


def test_default_candidate_pool_is_not_affected_by_body_variants():
    master = json.loads(MASTER.read_text())
    defaults = {**master, 'templates': [t for t in master['templates']
                                      if template_identity(t)[1:3] == ('standard', 'unisex')]}
    assert build_pool(master) == build_pool(defaults)


def test_delivery_binds_all_96_notes_and_569_items_to_material_ids():
    delivery = json.loads((ROOT / 'app/data/styling-delivery.v1.json').read_text())
    runtime = json.loads(RUNTIME.read_text())
    keys = set()
    for look in delivery['looks']:
        binding = look['note_binding']
        key = (binding['templateId'], binding['noteId'])
        assert key not in keys
        keys.add(key)
        template = {**runtime['types'], **runtime['variants']}[binding['templateId']]
        card = template['recommendations']['outfits']['items'][binding['position'] - 1]
        assert card['name'] == binding['name']
        assert card['image']['assetId'] == look['source_asset']['assetId']
        for item in look['items']:
            assert item['image_asset']['assetId'].startswith('asset_')
    assert len(keys) == 96
    assert sum(len(l['items']) for l in delivery['looks']) == 569


def test_runtime_images_resolve_without_private_editor_urls():
    registry = MaterialRegistry()
    runtime = resolve_image_references(json.loads(RUNTIME.read_text()), registry)
    def check(value):
        if isinstance(value, dict):
            for id_field, url_field in IMAGE_ID_FIELDS.items():
                if value.get(id_field):
                    assert value[url_field] == asset_content_url(value[id_field])
                    source = material_source_url(registry.get(value[id_field]))
                    assert not source.startswith('/api/assets/')
                    if source.startswith('/static/'):
                        assert (ROOT / 'app' / urlsplit(source).path.lstrip('/')).is_file()
            for key, item in value.items():
                if key in {'src', 'imageUrl'} and item:
                    assert not item.startswith('/api/assets/')
                    if item.startswith('/static/'):
                        assert (ROOT / 'app' / urlsplit(item).path.lstrip('/')).is_file()
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
    check(runtime)


def test_oss_adapter_checks_bucket_and_preserves_content_type():
    class Bucket:
        bucket_name = 'approved-materials'
        def put_object(self, key, data, headers):
            return key, data, headers
    adapter = OssUploadClient(Bucket())
    assert adapter.put_object(Bucket='approved-materials', Key='a.png', Body=b'png', ContentType='image/png') == (
        'a.png', b'png', {'Content-Type': 'image/png'})
    with pytest.raises(ValueError, match='destination'):
        adapter.put_object(Bucket='wrong', Key='a.png', Body=b'png', ContentType='image/png')

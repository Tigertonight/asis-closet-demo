import contextlib
import io
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import app.material_assets as materials
import app.material_asset_signing as signing
from scripts.upload_content_pool import upload_directory

STORAGE = {'provider': 'qiniu', 'bucket': 'materials', 'key': 'a.png', 'private': True}


@pytest.fixture
def registry(monkeypatch, tmp_path):
    monkeypatch.setattr(materials, 'ROOT', tmp_path)
    monkeypatch.setenv('QINIU_ACCESS_KEY', 'test-ak')
    monkeypatch.setenv('QINIU_SECRET_KEY', 'test-sk')
    monkeypatch.setenv('QINIU_ENV_FILE', str(tmp_path / 'missing.env'))
    monkeypatch.setenv('QINIU_MATERIAL_URL_TTL_SECONDS', '604800')
    registry = materials.MaterialRegistry(tmp_path / 'materials.json')
    monkeypatch.setenv('SELFIT_MATERIAL_REGISTRY_PATH', str(registry.path))
    return registry


def register_image(registry):
    output = io.BytesIO()
    Image.new('RGB', (2, 3), 'red').save(output, format='PNG')
    data = output.getvalue()
    asset_id = registry.register(data, 'http://example.com/a.png', 'image/png', storage=STORAGE)
    return asset_id, data


def client():
    app = FastAPI()
    app.include_router(materials.router)
    return TestClient(app)


def test_new_machine_reads_published_url_without_keys_or_cache(registry, monkeypatch):
    asset_id, data = register_image(registry)
    saved_url = registry.get(asset_id)['url']
    assert not (materials.ROOT / 'outputs/material-cache').exists()
    monkeypatch.setenv('QINIU_ACCESS_KEY', '')
    monkeypatch.setenv('QINIU_SECRET_KEY', '')
    def no_signing(*args, **kwargs):
        raise AssertionError('Reading must never sign URLs')
    monkeypatch.setattr(signing, 'sign_qiniu_url', no_signing)
    requested = []
    @contextlib.contextmanager
    def download(method, url, **kwargs):
        requested.append(url)
        yield httpx.Response(200, content=data, request=httpx.Request(method, url))
    monkeypatch.setattr(httpx, 'stream', download)
    browser = client()
    metadata = browser.get(f'/api/v1/material-assets/{asset_id}')
    assert metadata.status_code == 200
    assert metadata.json()['url'] == saved_url
    assert metadata.json()['urlExpiresAt'] == registry.get(asset_id)['urlExpiresAt']
    image = browser.get(materials.asset_content_url(asset_id))
    assert image.status_code == 200 and image.content == data
    assert requested == [saved_url]
    assert 'location' not in image.headers  # HTTP origin remains usable on HTTPS pages.


def test_expired_url_reports_error_and_owner_can_refresh_same_id(registry, monkeypatch):
    asset_id, _ = register_image(registry)
    previous = registry.get(asset_id)
    monkeypatch.setattr(materials.time, 'time', lambda: previous['urlExpiresAt'] + 1)
    browser = client()
    for endpoint in (f'/api/v1/material-assets/{asset_id}', materials.asset_content_url(asset_id)):
        response = browser.get(endpoint)
        assert response.status_code == 410
        assert response.json()['error']['code'] == 'material.url_expired'
        assert response.headers['cache-control'] == 'no-store'
    assert registry.refresh_temporary_urls() == 1
    refreshed = browser.get(f'/api/v1/material-assets/{asset_id}').json()
    assert refreshed['assetId'] == asset_id
    assert refreshed['url'] != previous['url']
    assert refreshed['sourceUrl'] == previous['sourceUrl']
    assert refreshed['url'].count('token=') == refreshed['url'].count('e=') == 1


def test_legacy_records_are_migrated_without_upload_or_loss_of_metadata(registry):
    asset_id, _ = register_image(registry)
    public_id = registry.register(b'public', '/static/public.png', 'image/png')
    payload = json.loads(registry.path.read_text())
    record = payload['assets'][asset_id]
    record['url'] = record.pop('sourceUrl')
    del record['urlExpiresAt']
    record['label'] = 'keep this'
    registry.path.write_text(json.dumps(payload))
    before = registry.get(public_id)
    response = client().get(f'/api/v1/material-assets/{asset_id}')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'material.url_not_published'
    assert registry.refresh_temporary_urls() == 1
    assert registry.get(asset_id)['label'] == 'keep this'
    assert registry.get(public_id) == before
    assert client().get(f'/api/v1/material-assets/{asset_id}').status_code == 200


def test_refresh_noop_and_signing_failure_leave_registry_unchanged(registry, monkeypatch):
    register_image(registry)
    before = registry.path.read_bytes()
    assert registry.refresh_temporary_urls() == 0
    assert registry.path.read_bytes() == before
    monkeypatch.setenv('QINIU_ACCESS_KEY', '')
    monkeypatch.setenv('QINIU_SECRET_KEY', '')
    with pytest.raises(ValueError, match='signing credentials'):
        registry.refresh_temporary_urls(force=True)
    assert registry.path.read_bytes() == before


def test_refresh_does_not_duplicate_existing_authorization_parameters(registry):
    asset_id, _ = register_image(registry)
    payload = json.loads(registry.path.read_text())
    del payload['assets'][asset_id]['sourceUrl']
    registry.path.write_text(json.dumps(payload))
    registry.refresh_temporary_urls(force=True)
    updated = registry.get(asset_id)
    assert updated['sourceUrl'] == 'http://example.com/a.png'
    assert updated['url'].count('token=') == 1


def test_upload_resume_uses_source_url_and_renews_without_resending_bytes(registry, monkeypatch, tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'a.png').write_bytes(b'picture')
    class Upload:
        calls = 0
        def put_object(self, **kwargs):
            self.calls += 1
        def storage_metadata(self, key):
            return {**STORAGE, 'key': key}
    uploader = Upload()
    args = dict(client=uploader, bucket='materials', public_base='http://example.com', registry=registry)
    first = upload_directory(source, **args)
    asset_id = first['files']['a.png']['assetId']
    expiry = registry.get(asset_id)['urlExpiresAt']
    assert upload_directory(source, **args) == first
    assert uploader.calls == 1
    monkeypatch.setattr(materials.time, 'time', lambda: expiry + 1)
    assert upload_directory(source, **args) == first
    assert uploader.calls == 1
    assert registry.get(asset_id)['urlExpiresAt'] > expiry


def test_indirect_references_remain_stable_after_url_expiry(registry, monkeypatch):
    asset_id, _ = register_image(registry)
    expires_at = registry.get(asset_id)['urlExpiresAt']
    monkeypatch.setattr(materials.time, 'time', lambda: expires_at + 1)
    reference = {'assetId': asset_id}
    assert materials.resolve_image_references(reference, registry)['src'] == materials.asset_content_url(asset_id)
    with pytest.raises(materials.MaterialUrlUnavailable):
        materials.resolve_image_references(reference, registry, indirect=False)

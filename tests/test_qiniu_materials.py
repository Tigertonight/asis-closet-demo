import hashlib
import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import app.material_assets as materials
from app.material_assets import MaterialRegistry, material_download_url, router
from scripts.qiniu_material_upload import QiniuUploadClient


def test_qiniu_upload_checks_destination_and_checksum(monkeypatch):
    qiniu = pytest.importorskip('qiniu')
    from qiniu.utils import etag_stream
    client = QiniuUploadClient(bucket='test-materials', access_key='test-ak', secret_key='test-sk',
                               upload_host='https://upload.qiniup.com')
    calls = []
    def put_data(token, key, data, **kwargs):
        calls.append(kwargs)
        return {'key': key, 'hash': etag_stream(io.BytesIO(data))}, SimpleNamespace(status_code=200)
    monkeypatch.setattr(qiniu, 'put_data', put_data)
    args = dict(Bucket='test-materials', Key='images/a.png', Body=b'image', ContentType='image/png')
    client.put_object(**args)
    assert calls[0]['mime_type'] == 'image/png'
    assert client.storage_metadata(args['Key'])['private'] is True
    with pytest.raises(ValueError, match='destination'):
        client.put_object(**{**args, 'Bucket': 'another-bucket'})
    monkeypatch.setattr(qiniu, 'put_data', lambda *a, **kw: ({'key': 'images/a.png', 'hash': 'wrong'}, SimpleNamespace(status_code=200)))
    with pytest.raises(RuntimeError, match='checksum'):
        client.put_object(**args)


def test_private_download_signing_matches_official_sdk_without_storing_token(monkeypatch, tmp_path):
    qiniu = pytest.importorskip('qiniu')
    monkeypatch.setenv('QINIU_ACCESS_KEY', 'test-ak')
    monkeypatch.setenv('QINIU_SECRET_KEY', 'test-sk')
    monkeypatch.setenv('QINIU_ENV_FILE', str(tmp_path / 'unused.env'))
    monkeypatch.setattr(materials.time, 'time', lambda: 1788900000)
    record = {'url': 'http://example.com/path/a.png', 'storage': {'provider': 'qiniu', 'private': True}}
    expected = qiniu.Auth('test-ak', 'test-sk').private_download_url(record['url'], expires=3600)
    assert material_download_url(record) == expected
    assert '?' not in record['url']


def test_private_material_is_served_from_verified_cache_without_redirect_or_token(monkeypatch, tmp_path):
    monkeypatch.setattr(materials, 'ROOT', tmp_path)
    registry = MaterialRegistry(tmp_path / 'materials.json')
    monkeypatch.setenv('SELFIT_MATERIAL_REGISTRY_PATH', str(registry.path))
    raw = io.BytesIO()
    Image.new('RGB', (2, 2)).save(raw, format='PNG')
    data = raw.getvalue()
    asset_id = registry.register(data, 'http://example.com/a.png', 'image/png',
                                 storage={'provider': 'qiniu', 'bucket': 'materials', 'key': 'a.png', 'private': True})
    cache = tmp_path / 'outputs/material-cache'
    cache.mkdir(parents=True)
    (cache / (asset_id + '.image')).write_bytes(data)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get(f'/api/v1/material-assets/{asset_id}/content')
    assert response.status_code == 200
    assert response.content == data
    assert 'location' not in response.headers
    assert 'token=' not in registry.path.read_text()
    (cache / (asset_id + '.image')).write_bytes(b'corrupt')
    response = TestClient(app).get(f'/api/v1/material-assets/{asset_id}/content')
    assert response.status_code == 503

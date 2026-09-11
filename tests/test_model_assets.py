import json
import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import model_assets
from app.material_assets import MaterialRegistry, asset_content_url


def test_asset_model_overrides_old_local_file_and_works_without_it(tmp_path, monkeypatch):
    registry = MaterialRegistry(tmp_path / 'assets.json')
    aid = registry.register(b'current-model', '/static/current-model.png', 'image/png')
    monkeypatch.setattr(model_assets, 'MaterialRegistry', lambda: registry)
    old = tmp_path / 'female_medium_1.png'
    old.write_bytes(b'old-model')
    (tmp_path / 'manifest.json').write_text(json.dumps({'items': [
        {'file': old.name, 'image_asset_id': aid},
    ]}))
    app = FastAPI()
    app.mount('/tryon-models', model_assets.ModelStaticFiles(directory=tmp_path))
    client = TestClient(app)
    for exists in (True, False):
        if not exists:
            old.unlink()
        response = client.get('/tryon-models/' + old.name + '?v=legacy', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'] == asset_content_url(aid)
        assert response.headers['cache-control'] == 'no-cache'


def test_local_models_keep_static_fallback_and_path_boundaries(tmp_path):
    directory = tmp_path / 'models'
    directory.mkdir()
    (directory / 'manifest.json').write_text(json.dumps({'items': [{'file': 'local.png'}]}))
    (directory / 'local.png').write_bytes(b'local-model')
    (tmp_path / 'secret.txt').write_text('outside-model-directory')
    app = FastAPI()
    app.mount('/tryon-models', model_assets.ModelStaticFiles(directory=directory))
    client = TestClient(app)
    assert client.get('/tryon-models/local.png').content == b'local-model'
    assert client.get('/tryon-models/%2e%2e/secret.txt').status_code == 404


def test_local_metadata_requires_exact_original_and_does_not_change_shared_manifest(tmp_path):
    shared = {'items': [{'file': 'female.png', 'gender': 'female', 'width': 1024}]}
    (tmp_path / 'manifest.json').write_text(json.dumps(shared))
    source = tmp_path / 'female.png'
    source.write_bytes(b'private-local-original')
    (tmp_path / 'manifest.local.json').write_text(json.dumps({'models': {'female': {
        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'metadata': {'file': 'female.png', 'gender': 'female', 'width': 1792},
    }}}))
    assert model_assets.load_model_manifest(tmp_path)['items'][0]['width'] == 1792
    assert json.loads((tmp_path / 'manifest.json').read_text()) == shared
    source.write_bytes(b'shared-git-original')
    assert model_assets.load_model_manifest(tmp_path) == shared

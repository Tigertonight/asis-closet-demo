import hashlib
import json

import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.model_assets import ModelStaticFiles, load_model_manifest
from scripts.prepare_runtime_tryon_models import prepare


@pytest.fixture
def model_bundle(tmp_path):
    shared, originals = tmp_path / 'shared', tmp_path / 'originals'
    shared.mkdir(); originals.mkdir()
    Image.new('RGB', (20, 30), 'white').save(shared / 'female.png')
    Image.new('RGB', (20, 30), 'blue').save(shared / 'male.png')
    Image.new('RGB', (30, 40), 'red').save(originals / 'female.png')
    manifest = {'items': [{'file': 'female.png', 'gender': 'female', 'width': 20, 'height': 30},
                          {'file': 'male.png', 'gender': 'male'},
                          {'id': 'remote', 'file': 'remote.png', 'image_asset_id': 'asset_' + 'a' * 64}]}
    (shared / 'manifest.json').write_text(json.dumps(manifest))
    metadata = {'file': 'female.png', 'gender': 'female', 'width': 30, 'height': 40}
    overrides = tmp_path / 'overrides.json'
    overrides.write_text(json.dumps({'models': {'female': {
        'sha256': hashlib.sha256((originals / 'female.png').read_bytes()).hexdigest(), 'metadata': metadata}}}))
    return shared, originals, overrides, tmp_path / 'runtime'


def test_runtime_uses_exact_original_and_preserves_other_models_and_git_files(model_bundle):
    shared, originals, overrides, output = model_bundle
    before = {p.name: p.read_bytes() for p in shared.iterdir()}
    result = prepare(*model_bundle)
    from pathlib import Path
    directory = Path(result['directory'])
    rows = load_model_manifest(directory)['items']
    assert rows[0]['width'] == 30
    assert rows[1:] == json.loads(before['manifest.json'])['items'][1:]
    assert (directory / 'male.png').read_bytes() == before['male.png']
    assert {p.name: p.read_bytes() for p in shared.iterdir()} == before
    app = FastAPI()
    app.mount('/tryon-models', ModelStaticFiles(directory=directory))
    response = TestClient(app).get('/tryon-models/female.png?format=original')
    assert response.content == (originals / 'female.png').read_bytes()
    assert prepare(*model_bundle) == result


@pytest.mark.parametrize('invalid', ['hash', 'dimensions', 'unknown_model', 'path'])
def test_invalid_original_is_rejected_before_runtime_directory_is_created(model_bundle, invalid):
    shared, originals, overrides, output = model_bundle
    data = json.loads(overrides.read_text())
    row = data['models']['female']
    if invalid == 'hash': row['sha256'] = '0' * 64
    if invalid == 'dimensions': row['metadata']['height'] = 400
    if invalid == 'unknown_model': data['models']['unknown'] = data['models'].pop('female')
    if invalid == 'path': row['metadata']['file'] = '../outside.png'
    overrides.write_text(json.dumps(data))
    with pytest.raises(ValueError): prepare(*model_bundle)
    assert not output.exists()


def test_changed_runtime_bytes_are_rejected_and_new_manifest_creates_new_version(model_bundle):
    from pathlib import Path
    shared, originals, overrides, _ = model_bundle
    first = Path(prepare(*model_bundle)['directory'])
    old = (first / 'female.png').read_bytes()
    (first / 'female.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Runtime original changed'): prepare(*model_bundle)
    (first / 'female.png').write_bytes(old)
    data = json.loads((shared / 'manifest.json').read_text())
    data['items'][1]['display_name'] = 'Updated male name'
    (shared / 'manifest.json').write_text(json.dumps(data))
    second = Path(prepare(*model_bundle)['directory'])
    assert first != second
    assert (first / 'female.png').read_bytes() == old
    assert load_model_manifest(second)['items'][1]['display_name'] == 'Updated male name'

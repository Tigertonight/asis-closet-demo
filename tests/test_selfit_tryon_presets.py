import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth, closet, storage, tryon, selfit_tryon_presets as presets
from app.auth import get_current_user
from app.beta_access import require_beta_tryon, require_beta_user
from app.main import app
from app.styling_catalog import delivery_looks, adapt_outfit


@pytest.fixture
def preset_case(monkeypatch, tmp_path):
    source = json.loads(presets.INDEX_PATH.read_text())
    example = copy.deepcopy(next(row for row in source['examples']
        if row['id'] == 'female_medium_1--bolt--outfits-01'))
    path = tmp_path / 'presets.json'
    monkeypatch.setattr(presets, 'INDEX_PATH', path)
    monkeypatch.setattr(presets, 'material_download_url', lambda record: '/verified.png')
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path / 'users')
    monkeypatch.setattr(auth, 'AUTH_DIR', tmp_path / 'auth')
    look = next(row for row in delivery_looks()
        if row['note_binding']['templateId'] == 'bolt' and row['note_binding']['noteId'] == 'outfits-01')
    outfit = adapt_outfit(look)
    from app.material_assets import material_image_path
    masters = json.loads((tryon.TRYON_MODEL_FIXTURE_DIR / 'manifest.json').read_text())['items']
    current = next(m for m in masters if (m.get('id') or Path(m['file']).stem) == example['modelId'])
    source = material_image_path(current['image_asset_id']) if current.get('image_asset_id') else tryon.TRYON_MODEL_FIXTURE_DIR / current['file']
    raw = source.read_bytes()
    # Model photos can be replaced independently of historical published results.
    # Only this isolated test catalog represents a preset for the current photo.
    example['model']['sha256'] = hashlib.sha256(raw).hexdigest()
    if current.get('image_asset_id'):
        example['model']['image_asset_id'] = current['image_asset_id']
    path.write_text(json.dumps({'examples': [example]}))
    return example, outfit, raw, path


def test_matches_model_and_note_after_cutout_asset_update(preset_case):
    example, outfit, raw, _ = preset_case
    assert example['outfitId'] != outfit['outfit_id'], 'cutout updates changed the runtime outfit ID'
    found = presets.find_preset(outfit['outfit_id'], example['modelId'], raw, outfit['item_ids'])
    assert found['example_id'] == example['id']
    assert found['outfit']['outfit_id'] == outfit['outfit_id']
    assert found['image_path'] == example['result']['contentUrl']


@pytest.mark.parametrize('case', ['self', 'different_photo', 'different_model', 'partial',
    'edited_outfit', 'variant', 'changed_note', 'changed_items', 'failed', 'unverified', 'missing_asset'])
def test_only_exact_usable_presets_match(preset_case, monkeypatch, case):
    example, outfit, raw, path = preset_case
    model, oid, ids = example['modelId'], outfit['outfit_id'], outfit['item_ids']
    if case == 'self': model = 'self'
    if case == 'different_photo': raw += b'changed'
    if case == 'different_model': model = 'female_slim_1'
    if case == 'partial': ids = ids[:-1]
    if case == 'edited_outfit': oid = 'saved-personal-outfit'
    if case == 'variant': example['noteBinding']['templateId'] = 'bolt-curvy'
    if case == 'changed_note': example['sourceAssetId'] = 'asset_changed'
    if case == 'changed_items': example['itemIds'] = example['itemIds'][:-1]
    if case == 'failed': example['status'] = 'failed_quality'
    if case == 'unverified': example['result']['verified'] = False
    if case == 'missing_asset': example['result']['assetId'] = 'asset_' + '0' * 64
    path.write_text(json.dumps({'examples': [example]}))
    assert presets.find_preset(oid, model, raw, ids) is None


def test_job_uses_preset_without_generation_and_keeps_history(preset_case, monkeypatch):
    example, outfit, raw, _ = preset_case
    submitted = []
    class Executor:
        def submit(self, *args): submitted.append(args)
    monkeypatch.setattr(tryon, 'TRYON_JOB_EXECUTOR', Executor())
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'preset-test'}
    app.dependency_overrides[require_beta_user] = lambda: {'user_id': 'preset-test', 'beta_qualified': True}
    app.dependency_overrides[require_beta_tryon] = lambda: {'user_id': 'preset-test', 'beta_qualified': True}
    try:
        client = TestClient(app)
        data = {'outfit_id': outfit['outfit_id'], 'model_id': example['modelId'],
                'selected_item_ids': json.dumps(outfit['item_ids']), 'wear_all_items': 'true',
                'client_request_id': 'preset-request'}
        files = {'person_image': (example['model']['file'], raw, 'image/png')}
        response = client.post('/selfit/try-on/jobs', data=data, files=files)
        assert response.status_code == 200, response.text
        job = response.json()
        assert job['status'] == 'completed'
        assert job['result']['generation_strategy'] == 'preset'
        assert job['result']['result']['image_path'] == example['result']['contentUrl']
        assert job['result']['record']['original_image_path'] == job['original_image_path']
        assert job['result']['record']['generation_strategy'] == 'preset'
        assert submitted == [], 'no image-generation worker or model API is called'
        assert client.get('/selfit/try-on/jobs/' + job['job_id']).json()['result'] == job['result']
        assert client.post('/selfit/try-on/jobs', data=data, files=files).json()['job_id'] == job['job_id']
        assert submitted == []
        # Force regeneration and personal photos keep the original worker path.
        for key, changes in [('force', {'force_regenerate': 'true'}), ('self', {'model_id': 'self'})]:
            result = client.post('/selfit/try-on/jobs', data={**data, **changes, 'client_request_id': key}, files=files)
            assert result.json()['status'] == 'queued'
        assert len(submitted) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_beta_user, None)
        app.dependency_overrides.pop(require_beta_tryon, None)


@pytest.fixture
def male_asset_case(preset_case, monkeypatch):
    """A registered model need not exist in the legacy fixture directory."""
    example, _, _, path = preset_case
    master=json.loads((tryon.TRYON_MODEL_FIXTURE_DIR/'manifest.json').read_text())
    model=next(m for m in master['items'] if m.get('id')=='male_standard_1')
    from app.material_assets import material_image_path
    raw=material_image_path(model['image_asset_id']).read_bytes()
    import hashlib
    look=next(x for x in delivery_looks() if x['note_binding']['templateId']=='ease-male')
    outfit=adapt_outfit(look)
    example.update(id='male-preset-fixture',modelId=model['id'],model={**model,'sha256':hashlib.sha256(raw).hexdigest()},
                   noteBinding=look['note_binding'],sourceAssetId=look['source_asset']['assetId'],
                   itemIds=[x['item_id'] for x in look['items']],inputAssetIds=[x['image_asset']['assetId'] for x in look['items']])
    path.write_text(json.dumps({'examples':[example]}))
    return example,outfit,raw,path


def test_asset_model_matches_without_fixture_file(male_asset_case):
    example,outfit,raw,_=male_asset_case
    assert not (tryon.TRYON_MODEL_FIXTURE_DIR/example['model']['file']).exists()
    assert presets.find_preset(outfit['outfit_id'],example['modelId'],raw,outfit['item_ids'])['example_id']==example['id']


@pytest.mark.parametrize('change',['input_asset','model_asset','photo','partial'])
def test_asset_model_rejects_stale_inputs(male_asset_case,change):
    example,outfit,raw,path=male_asset_case
    ids=outfit['item_ids']
    if change=='input_asset':example['inputAssetIds'][0]='asset_changed'
    if change=='model_asset':example['model']['image_asset_id']='asset_changed'
    if change=='photo':raw+=b'changed'
    if change=='partial':ids=ids[:-1]
    path.write_text(json.dumps({'examples':[example]}))
    assert presets.find_preset(outfit['outfit_id'],example['modelId'],raw,ids) is None


def test_asset_model_job_uses_preset_and_keeps_history(male_asset_case,monkeypatch):
    test_job_uses_preset_without_generation_and_keeps_history(male_asset_case,monkeypatch)

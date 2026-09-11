"""Account gender drives model selection without another first-paint request."""
import json

import pytest
from fastapi.testclient import TestClient
from app import closet, storage, tryon
from app.auth import get_current_user
from app.main import app
from app.material_assets import MaterialRegistry
from app.selfit_studio import model_library


@pytest.mark.parametrize('gender, expected', [('male','male'),('female','female'),(None,'female')])
def test_preferences_return_account_gender_without_overwriting_model_choice(monkeypatch, tmp_path, gender, expected):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    user = {'user_id': 'model-gender-test', 'gender': gender}
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    with storage.user_storage(user['user_id']):
        closet.update_user_preferences({'current_model_id':'self'})
    response = TestClient(app).get('/closet/preferences')
    assert response.status_code == 200
    assert response.json()['gender'] == expected
    assert response.json()['current_model_id'] == 'self'
    user['gender'] = 'female' if expected == 'male' else 'male'
    assert TestClient(app).get('/closet/preferences').json()['gender'] == user['gender']


def test_model_asset_does_not_require_a_local_photo_in_git(monkeypatch, tmp_path):
    registry = MaterialRegistry(tmp_path / 'assets.json')
    asset_id = registry.register(b'model-test-image', '/static/model-test.png', 'image/png')
    from app import material_assets
    monkeypatch.setattr(material_assets, 'MaterialRegistry', lambda: registry)
    row = {'id':'male_standard_1','file':'not-in-git.png','image_asset_id':asset_id,'gender':'male',
           'display_name':'男标准型','default_for_gender':True,'active':True}
    (tmp_path/'manifest.json').write_text(json.dumps({'items':[
        row,{**row,'id':'disabled','active':False},
        {**row,'id':'missing','image_asset_id':'asset_'+'0'*64},
    ]}))
    monkeypatch.setattr(tryon, 'TRYON_MODEL_FIXTURE_DIR', tmp_path)
    result = model_library()
    assert result['total'] == 1
    assert result['items'][0]['id'] == 'male_standard_1'
    assert result['items'][0]['default_for_gender'] is True
    assert result['items'][0]['image_url'] == f'/api/v1/material-assets/{asset_id}/content'


def test_published_male_model_can_be_selected_and_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda:{'user_id':'male-model-test','gender':'male'})
    client = TestClient(app)
    male = next(row for row in client.get('/selfit/try-on/models').json()['items'] if row['id']=='male_standard_1')
    assert male['gender'] == 'male'
    assert male['image_url'].startswith('/api/v1/material-assets/asset_')
    response = client.put('/selfit/try-on/model', json={'model_id':male['id']})
    assert response.status_code == 200
    assert response.json()['model']['image_url'] == male['image_url']
    assert client.get('/closet/preferences').json()['current_model_id'] == male['id']

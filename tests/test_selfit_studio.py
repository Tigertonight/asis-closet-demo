"""Library -> personal selection must preserve garment IDs/assets and user isolation."""
from copy import deepcopy
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import closet, storage
from app.auth import get_current_user
from app.main import app
from app.selfit_studio import StudioOutfit, save_studio_outfit

@pytest.fixture
def library(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    rows = [x for x in closet._published_catalog_outfits() if x.get('tryon_ready')]
    assert rows
    sample = deepcopy(rows[0])
    monkeypatch.setattr(closet, '_published_catalog_outfits', lambda **kw: [deepcopy(sample)])
    return sample


def test_library_selection_round_trip_and_retry(library):
    ids=library['item_ids']
    with storage.user_storage('studio_test_a'):
        saved=save_studio_outfit(StudioOutfit(item_ids=ids, favorite=True))
        resolved=closet.get_outfit(saved['outfit_id'])
        assert resolved['item_ids']==ids
        assert [x['assets'] for x in resolved['items']]==[x['assets'] for x in library['items']]
        assert resolved['favorite'] is True
        again=save_studio_outfit(StudioOutfit(item_ids=ids))
        assert again['outfit_id']==saved['outfit_id']
        plan,_=closet.outfit_as_tryon_plan(saved['outfit_id'])
        assert {x['item_id'] for x in plan['items']}==set(ids)
    with storage.user_storage('studio_test_b'):
        with pytest.raises(HTTPException): closet.get_outfit(saved['outfit_id'])


def test_reject_unknown_piece_before_copying_anything(library):
    with storage.user_storage('studio_test_invalid'):
        with pytest.raises(HTTPException):
            save_studio_outfit(StudioOutfit(item_ids=[library['item_ids'][0], 'another_users_private_item']))
        assert closet._ensure_manifest()['items']==[]


def test_wardrobe_does_not_treat_library_tryon_as_ownership(library):
    from app.selfit_studio import personal_wardrobe
    with storage.user_storage('studio_empty_wardrobe'):
        assert personal_wardrobe() == {'items': [], 'outfits': []}
        saved = save_studio_outfit(StudioOutfit(item_ids=library['item_ids']))
        assert personal_wardrobe() == {'items': [], 'outfits': []}
        closet.update_outfit(saved['outfit_id'], {'favorite': True})
        wardrobe = personal_wardrobe()
        assert wardrobe['items'] == []
        assert [row['outfit_id'] for row in wardrobe['outfits']] == [saved['outfit_id']]
        closet.update_outfit(saved['outfit_id'], {'favorite': False})
        assert personal_wardrobe() == {'items': [], 'outfits': []}


def test_uploaded_anchor_generation_and_user_isolation(library, monkeypatch):
    from app.selfit_studio import personal_wardrobe, studio_item_outfits
    from app import recommendation_profile
    monkeypatch.setattr(recommendation_profile, 'resolve_profile', lambda user_id: {'persona_id': None})
    with storage.user_storage('studio_anchor_owner'):
        anchor = deepcopy(library['items'][0])
        anchor.update(item_id='uploaded_anchor', source={'type': 'upload'})
        manifest = closet._ensure_manifest()
        manifest['items'].append(anchor)
        closet._write_manifest(manifest)
    result = studio_item_outfits('uploaded_anchor', {'user_id': 'studio_anchor_owner'})
    assert result['outfits']
    for row in result['outfits']:
        assert 'uploaded_anchor' in row['item_ids']
        assert library['items'][0]['item_id'] not in row['item_ids']
    with storage.user_storage('studio_anchor_owner'):
        wardrobe = personal_wardrobe()
        assert [item['item_id'] for item in wardrobe['items']] == ['uploaded_anchor']
        assert wardrobe['outfits']
    with pytest.raises(HTTPException) as error:
        studio_item_outfits('uploaded_anchor', {'user_id': 'studio_anchor_other'})
    assert error.value.status_code == 404


def test_legacy_app_link_routes_to_mirror_detail():
    client = TestClient(app)
    response = client.get('/wearwow/demo?outfit=sample', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/selfit/try-on?screen=detail&outfit=sample'


def test_inspiration_recommendation_does_not_read_private_outfits(library, monkeypatch):
    with storage.user_storage('studio_source_boundary'):
        save_studio_outfit(StudioOutfit(item_ids=library['item_ids'], favorite=True))
        def unexpected_private_read():
            raise AssertionError('Inspiration must only rank published outfits')
        monkeypatch.setattr(closet, 'list_outfits', unexpected_private_read)
        result = closet.recommend_outfits({'source': 'inspiration', 'limit': 12})
        assert result['outfits']
        assert {row['outfit_id'] for row in result['outfits']} == {library['outfit_id']}


def test_route_requires_auth_and_rejects_too_many_items(library):
    client=TestClient(app)
    assert client.post('/selfit/try-on/outfits',json={'item_ids':library['item_ids']}).status_code==401
    app.dependency_overrides[get_current_user]=lambda:{'user_id':'studio_route_test'}
    try:
        assert client.post('/selfit/try-on/outfits',json={'item_ids':['x']*9}).status_code==422
        r=client.post('/selfit/try-on/outfits',json={'item_ids':library['item_ids']})
        assert r.status_code==200
        assert client.get('/closet/outfits/'+r.json()['outfit_id']).json()['item_ids']==library['item_ids']
    finally: app.dependency_overrides.pop(get_current_user,None)


def test_model_master_data_filters_and_sorts(monkeypatch, tmp_path):
    import json
    from PIL import Image
    from app import tryon
    from app.selfit_studio import model_library
    for name in ['first.png','second.png','hidden.png']:
        Image.new('RGB',(4,6)).save(tmp_path/name)
    (tmp_path/'manifest.json').write_text(json.dumps({'items':[
        {'file':'second.png','display_name':'主数据名称','active':True,'sort_order':2},
        {'file':'hidden.png','active':False,'sort_order':0},
        {'file':'first.png','active':True,'sort_order':1},
        {'file':'missing.png'}, {'file':'../outside.png'},
    ]}))
    monkeypatch.setattr(tryon,'TRYON_MODEL_FIXTURE_DIR',tmp_path)
    result=model_library()
    assert [x['id'] for x in result['items']]==['first','second']
    assert result['items'][1]['name']=='主数据名称'
    assert result['items'][0]['image_url'].startswith('/tryon-models/first.png?v=')


def test_model_selection_persists_and_rejects_unavailable(monkeypatch, tmp_path):
    from app import selfit_studio
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    monkeypatch.setattr(selfit_studio,'model_library',lambda:{'items':[{'id':'master_a','image_url':'/tryon-models/master_a.png','name':'模特 A'}]})
    client=TestClient(app)
    assert client.put('/selfit/try-on/model',json={'model_id':'master_a'}).status_code==401
    app.dependency_overrides[get_current_user]=lambda:{'user_id':'model_user'}
    try:
        assert client.put('/selfit/try-on/model',json={'model_id':'master_a'}).json()['model']['id']=='master_a'
        assert client.get('/closet/preferences').json()['current_model_id']=='master_a'
        assert client.put('/selfit/try-on/model',json={'model_id':'disabled_model'}).status_code==404
        assert client.get('/closet/preferences').json()['current_model_id']=='master_a'
        assert client.put('/selfit/try-on/model',json={'model_id':'self'}).status_code==200
    finally: app.dependency_overrides.pop(get_current_user,None)


def test_delete_outfit_persists_without_deleting_pieces(library):
    client=TestClient(app)
    user={'user_id':'outfit_delete_owner'}
    app.dependency_overrides[get_current_user]=lambda:user
    try:
        saved=client.post('/selfit/try-on/outfits',json={'item_ids':library['item_ids']}).json()
        oid=saved['outfit_id']
        assert saved['can_delete'] is True
        # Other accounts cannot remove this outfit.
        user['user_id']='outfit_delete_other'
        assert client.delete('/closet/outfits/'+oid).status_code==404
        user['user_id']='outfit_delete_owner'
        assert client.get('/closet/outfits/'+oid).status_code==200
        assert client.delete('/closet/outfits/'+oid).status_code==200
        assert client.get('/closet/outfits/'+oid).status_code==404
        assert all(x['outfit_id']!=oid for x in client.get('/closet/outfits').json()['outfits'])
        for iid in library['item_ids']:
            assert client.get('/closet/items/'+iid).status_code==200
        # A new request/context still sees the tombstone; repeated delete is harmless.
        assert client.delete('/closet/outfits/'+oid).status_code==404
        assert client.delete('/closet/outfits/'+library['outfit_id']).status_code==404
        assert client.get('/closet/outfits/'+library['outfit_id']).status_code==200
    finally: app.dependency_overrides.pop(get_current_user,None)

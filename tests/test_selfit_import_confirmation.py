import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.auth import get_current_user
from app import closet, storage


def test_upload_waits_for_selection_and_confirm_is_owned_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    class ImmediateExecutor:
        def submit(self, fn, *args): fn(*args)
    class Inventory:
        last_attempt = {'expected_count': 2}
        def extract_inventory(self, source, work_dir):
            return [{'item_id': 'candidate-'+category, 'category': category,
                     'source': {'image_id': source['image_id']}, 'quality': {'status':'usable'},
                     'assets': {'cutout_path':''}}
                    for category in ('top','bottom')]
    monkeypatch.setattr(closet, 'IMPORT_JOB_EXECUTOR', ImmediateExecutor())
    monkeypatch.setattr(closet, 'AIGarmentCutoutProvider', Inventory)
    user = {'user_id':'upload-alice'}
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    photo=io.BytesIO(); Image.new('RGB',(720,900),'white').save(photo,'PNG')
    try:
        response=client.post('/closet/import/jobs',data={'require_confirmation':'true'},files={'images':('look.png',photo.getvalue(),'image/png')})
        assert response.status_code == 200, response.text
        url='/closet/import/jobs/'+response.json()['job_id']
        draft=client.get(url).json()
        assert draft['status']=='awaiting_confirmation', draft
        assert len(draft['result']['items'])==2
        assert draft['result']['summary']['created']==0
        assert draft['result']['status']=='preview'
        with storage.user_storage(user['user_id']):
            assert closet._ensure_manifest()['items']==[]
            assert closet._ensure_outfit_manifest()['outfits']==[]
        assert client.post(url+'/confirm',json={'selected_item_ids':[]}).status_code==422
        assert client.post(url+'/confirm',json={'selected_item_ids':['not-in-this-upload']}).status_code==422
        user['user_id']='upload-bob'
        assert client.get(url).status_code==404
        assert client.post(url+'/confirm',json={'selected_item_ids':['candidate-top']}).status_code==404
        user['user_id']='upload-alice'
        body={'selected_item_ids':['candidate-top']}
        result=client.post(url+'/confirm',json=body)
        assert result.status_code==200, result.text
        assert result.json()['status']=='completed'
        assert [i['item_id'] for i in result.json()['result']['items']]==['candidate-top']
        assert client.post(url+'/confirm',json=body).json()==result.json()
        assert client.post(url+'/confirm',json={'selected_item_ids':['candidate-bottom']}).status_code==409
        with storage.user_storage(user['user_id']):
            assert [i['item_id'] for i in closet._ensure_manifest()['items']]==['candidate-top']
        # Re-uploading a partially saved photo must still offer its unselected pieces.
        second=client.post('/closet/import/jobs',data={'require_confirmation':'true'},files={'images':('look.png',photo.getvalue(),'image/png')}).json()
        again=client.get('/closet/import/jobs/'+second['job_id']).json()
        assert {i['item_id'] for i in again['result']['items']}=={'candidate-top','candidate-bottom'}
        with storage.user_storage(user['user_id']):
            assert [i['item_id'] for i in closet._ensure_manifest()['items']]==['candidate-top']
        with storage.user_storage(user['user_id']):
            removed=closet._ensure_manifest();removed['items'][0]['deleted']=True;closet._write_manifest(removed)
        third=client.post('/closet/import/jobs',data={'require_confirmation':'true'},files={'images':('look.png',photo.getvalue(),'image/png')}).json()
        third_url='/closet/import/jobs/'+third['job_id']
        assert client.post(third_url+'/confirm',json=body).status_code==200
        with storage.user_storage(user['user_id']):
            saved=closet._ensure_manifest()['items']
            assert len(saved)==1 and saved[0]['item_id']=='candidate-top' and not saved[0].get('deleted')
    finally:
        app.dependency_overrides.pop(get_current_user,None)

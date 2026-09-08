import io
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.auth import get_current_user
from app import selfit_inspiration, storage, tryon


def photo():
    out=io.BytesIO(); Image.new('RGB',(640,960),'pink').save(out,'PNG');return out.getvalue()


def test_note_job_persists_snapshot_and_retries_in_same_account(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    monkeypatch.setattr(selfit_inspiration,'resolve_profile',lambda uid:{'persona_id':'mute' if uid=='alice' else 'flou'})
    submitted=[]
    class Executor:
        def submit(self,*args): submitted.append(args)
    monkeypatch.setattr(tryon,'TRYON_JOB_EXECUTOR',Executor())
    client=TestClient(app);endpoint='/selfit/try-on/inspiration-jobs'
    note=selfit_inspiration.persona_notes('mute')[0]
    def post(note_id=note['id']):return client.post(endpoint,data={'note_id':note_id,'client_request_id':'stable'},files={'person_image':('a.png',photo(),'image/png')})
    assert post().status_code==401
    user={'user_id':'alice'};app.dependency_overrides[get_current_user]=lambda:user
    try:
        assert post('note:missing').status_code==404
        response=post();assert response.status_code==200,response.text
        job=response.json();assert job['kind']=='inspiration'
        assert job['note']==note and job['original_image_path'].startswith('/user-assets/tryon/')
        assert 'person_path' not in job and 'inspiration_path' not in job
        assert post().json()['job_id']==job['job_id'];assert len(submitted)==1
        url='/selfit/try-on/jobs/'+job['job_id']
        user['user_id']='bob';assert client.get(url).status_code==404;assert post().status_code==404
        user['user_id']='alice'
        generations=[]
        def generate(person,reference,**kwargs):
            assert kwargs['full_outfit'] is True
            path=tryon._tryon_output_dir()/'provider-result.png'
            Image.new('RGB',(64,96),'red' if not generations else 'blue').save(path)
            generations.append(path.read_bytes())
            return {'status':'generated','result':{'image_path':tryon._public_output_path(path)}}
        monkeypatch.setattr(tryon,'run_try_on_from_inspiration',generate)
        submitted[0][0](*submitted[0][1:])
        done=client.get(url).json();assert done['status']=='completed';assert done['result']['note']==note
        assert client.post(url+'/retry').status_code==200
        assert submitted[-1][0] is tryon._run_inspiration_tryon_job
        submitted[-1][0](*submitted[-1][1:])
        records=client.get('/closet/tryon-records').json()['records']
        assert len(records)==2 and all(row['note_id']==note['id'] and row['outfit_id'] is None for row in records)
        with storage.user_storage('alice'):
            first=tryon._tryon_result_disk_path(done['result']['result']['image_path'])
            assert first.read_bytes()==generations[0]
            assert first.read_bytes()!=generations[1]
        user['user_id']='bob';assert client.get('/closet/tryon-records').json()['records']==[]
        user['user_id']='alice'
        assert client.post(url+'/retry').status_code==200
        def fail(*args,**kwargs): raise RuntimeError('test failure')
        monkeypatch.setattr(tryon,'run_try_on_from_inspiration',fail)
        submitted[-1][0](*submitted[-1][1:])
        assert client.get(url).json()['status']=='failed'
        assert client.post(url+'/retry').json()['attempt']==4
    finally:app.dependency_overrides.pop(get_current_user,None)


def test_full_note_transfer_uses_full_body_mask_and_outfit_prompt(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    monkeypatch.setattr(tryon,'_input_quality_stage',lambda *a:tryon._stage('pass',1,{},[]))
    monkeypatch.setattr(tryon,'_detect_person',lambda *a:tryon._stage('pass',1,{'primary_face':{'box':{'x':275,'y':40,'width':90,'height':90}}},[]))
    monkeypatch.setattr(tryon,'_review_tryon_quality',lambda *a:tryon._stage('pass',1,{},[]))
    evidence={}
    class Provider:
        def edit(self,**kwargs):
            evidence.update(kwargs)
            result=kwargs['output_dir']/'result.png';Image.open(kwargs['person_image']).save(result)
            return {'stage':tryon._stage('pass',1,{},[]),'image_path':result}
    with storage.user_storage('alice'):
        person=tryon._read_upload_image(photo(),'a.png','person')
        note=tryon._read_upload_image(photo(),'b.png','inspiration')
        result=tryon.run_try_on_from_inspiration(person,note,provider=Provider(),full_outfit=True)
        assert result['status']=='generated';assert result['garment']['category']=='outfit'
        assert 'skirt/trousers or dress' in evidence['prompt'] and 'only that upper garment' not in evidence['prompt']
        alpha=Image.open(evidence['mask_image']).getchannel('A')
        assert alpha.getpixel((320,900))<128,'lower clothes/shoes must be editable'
        assert alpha.getpixel((320,60))>220,'face must stay protected'
        assert 'only that upper garment' in tryon._build_inspiration_tryon_prompt()

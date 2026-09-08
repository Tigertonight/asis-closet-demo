import io
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app import tryon, storage
from app.auth import get_optional_user


def test_job_source_photo_is_stable_and_account_scoped(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'ROOT_DIR',tmp_path)
    class HoldExecutor:
        def submit(self,*args): pass
    monkeypatch.setattr(tryon,'TRYON_JOB_EXECUTOR',HoldExecutor())
    buf=io.BytesIO();Image.new('RGB',(64,96),'pink').save(buf,'PNG');raw=buf.getvalue()
    with storage.user_storage('source-alice'):
        job=tryon.create_outfit_tryon_job(raw,'original.png','outfit-a','standard',None,'source-alice',client_request_id='stable')
        repeat=tryon.create_outfit_tryon_job(raw,'original.png','outfit-a','standard',None,'source-alice',client_request_id='stable')
        assert repeat['job_id']==job['job_id']
        assert repeat['original_image_path']==job['original_image_path']
        assert job['original_image_path'].startswith('/user-assets/tryon/job-inputs/')
    client=TestClient(app)
    assert client.get(job['original_image_path']).status_code==401
    user={'user_id':'source-alice'}
    app.dependency_overrides[get_optional_user]=lambda:user
    try:
        response=client.get(job['original_image_path']);assert response.status_code==200
        assert response.content==raw
        user['user_id']='source-bob'
        assert client.get(job['original_image_path']).status_code==404
    finally:
        app.dependency_overrides.pop(get_optional_user,None)

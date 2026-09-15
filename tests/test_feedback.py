import io
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from app import feedback
from app.auth import get_optional_user, get_admin_user


def client(monkeypatch,tmp_path):
    monkeypatch.setattr(feedback,'STORE',tmp_path)
    app=FastAPI();app.include_router(feedback.router)
    app.dependency_overrides[get_optional_user]=lambda:{'user_id':'user1'}
    return app,TestClient(app)


def test_feedback_text_photo_and_admin_permissions(monkeypatch,tmp_path):
    app,c=client(monkeypatch,tmp_path)
    data={'description':'测试问题','request_id':str(uuid.uuid4()),'source':'mirror?token=secret'}
    first=c.post('/api/v1/selfit/feedback',data=data);assert first.status_code==200
    assert c.post('/api/v1/selfit/feedback',data=data).status_code==200
    assert c.get('/admin/api/feedback').status_code in (401,403)
    app.dependency_overrides[get_admin_user]=lambda:{'user_id':'admin'}
    listing=c.get('/admin/api/feedback').json();assert listing['total']==1
    assert listing['items'][0]['source']=='mirror' and not listing['items'][0]['has_photo']
    image=io.BytesIO();Image.new('RGB',(20,30),'red').save(image,'PNG')
    data['request_id']=str(uuid.uuid4())
    result=c.post('/api/v1/selfit/feedback',data=data,files={'photo':('test.png',image.getvalue(),'image/png')})
    assert result.status_code==200
    url=f"/admin/api/feedback/{result.json()['id']}/photo"
    photo=c.get(url);assert photo.headers['content-type']=='image/webp'
    app.dependency_overrides.pop(get_admin_user)
    assert c.get(url).status_code in (401,403)


def test_feedback_validation(monkeypatch,tmp_path):
    _,c=client(monkeypatch,tmp_path)
    data={'description':'   ','request_id':str(uuid.uuid4())}
    assert c.post('/api/v1/selfit/feedback',data=data).status_code==422
    data['description']='test'
    assert c.post('/api/v1/selfit/feedback',data=data,files={'photo':('bad.png',b'not image','image/png')}).status_code==422
    assert c.post('/api/v1/selfit/feedback',data=data,files={'photo':('big.png',b'x'*(10*1024*1024+1),'image/png')}).status_code==413

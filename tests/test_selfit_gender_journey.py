"""Real authentication + onboarding + wardrobe routes share one declaration."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import auth, storage, selfit_onboarding as onboarding, selfit_report
from app.main import app
from app.material_assets import MaterialRegistry
from app.selfit_gender import declared_profile


@pytest.fixture(params=['json', 'sqlite'])
def journey(monkeypatch, tmp_path, request):
    monkeypatch.setenv('SELFIT_ONBOARDING_STORE_BACKEND', request.param)
    monkeypatch.setattr(onboarding, 'SELFIT_ONBOARDING_DIR', tmp_path/'onboarding')
    monkeypatch.setattr(onboarding, 'SELFIT_ONBOARDING_STORE_PATH', tmp_path/'onboarding/sessions.json')
    monkeypatch.setattr(auth, 'AUTH_DIR', tmp_path/'auth')
    monkeypatch.setattr(auth, 'AUTH_STORE_PATH', tmp_path/'auth/store.json')
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(MaterialRegistry, 'get', lambda *_: {'url':'/static/fixture.png'})
    monkeypatch.setattr(onboarding._REPORT_EXECUTOR, 'submit', lambda *_: None)
    user_id = 'gender-journey'
    token = 'test-only-gender-journey'
    auth._write_store({'users':[{'user_id':user_id,'gender':'female','status':'active'}],
                      'auth_sessions':[{'user_id':user_id,'status':'active','token_hash':auth._hash_secret(token),
                                        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}]})
    client = TestClient(app, headers={'Authorization':'Bearer '+token})
    session = client.post('/api/v1/selfit/sessions', json={'onboardingMode':'new'}).json()['session']
    return client, '/api/v1/selfit/sessions/'+session['sessionId'], user_id, token


def make_report(client, url, monkeypatch, persona='MUTE'):
    client.patch(url+'/preferences', json={'axes':{'shape':40,'energy':40,'trend':40}})
    response = client.post(url+'/report-jobs')
    assert response.status_code == 202
    monkeypatch.setattr(selfit_report.selfit_persona, 'classify_persona', lambda *_: {'primary_persona':persona})
    onboarding._run_report_job(response.json()['job']['jobId'])
    return onboarding._load_store()['reports'][-1]


def test_selection_reaches_auth_models_white_tee_and_report(journey, monkeypatch):
    client, url, user_id, token = journey
    assert client.get(url).json()['session']['gender'] is None
    assert client.post(url+'/photos/body').status_code == 422
    response = client.patch(url+'/gender', json={'gender':'male'})
    assert response.status_code == 200
    assert auth.resolve_token(token)['gender'] == 'male'
    assert client.get('/closet/preferences').json()['gender'] == 'male'
    profile = client.get('/api/v1/selfit/me/profile').json()['profile']
    assert profile['gender'] == 'male' and not profile['tested']
    rows = client.get('/selfit/try-on/report-outfits/home').json()['outfits']
    assert len(rows) == 4 and all(row['gender']=='male' for row in rows)
    # Exercise the real default-white-T matching path, with the shipped recipes.
    from app.selfit_outfit_match import _load_curated_white_tee
    anchor_id = _load_curated_white_tee()['anchor_item_id']
    monkeypatch.setattr('app.closet.get_closet_item', lambda _: {
        'item_id':anchor_id,'title':'白 T','category':'top','is_default':True})
    matched = client.post(f'/selfit/try-on/items/{anchor_id}/outfits')
    assert matched.status_code == 200, matched.text
    assert matched.json()['gender'] == 'male' and len(matched.json()['outfits']) == 3
    saved = make_report(client, url, monkeypatch)
    assert saved['data']['templateId'] == 'mute-male'
    assert client.get('/closet/preferences').json()['gender'] == 'male'
    assert all(x['template_id']=='mute-male' for x in client.get('/selfit/try-on/report-outfits/home').json()['outfits'])
    assert client.post('/api/v1/selfit/sessions', json={'onboardingMode':'retest'}).json()['session']['gender']=='male'


def test_edit_gender_updates_views_and_preserves_history_and_photos(journey, monkeypatch):
    client, url, user_id, token = journey
    client.patch(url+'/gender', json={'gender':'male'})
    saved = make_report(client, url, monkeypatch)
    before = onboarding._load_store()
    profile = client.get('/api/v1/selfit/me/profile').json()['profile']
    response = client.patch('/api/v1/selfit/me/gender', headers={'If-Match':str(profile['genderRevision'])}, json={'gender':'female'})
    assert response.status_code == 200
    assert response.json()['profile']['gender']=='female'
    assert auth.resolve_token(token)['gender']=='female'
    assert client.get('/closet/preferences').json()['gender']=='female'
    report = client.get('/api/v1/selfit/reports/'+saved['report_id']).json()['report']
    assert report['typeId']=='mute' and report['templateId']=='mute' and report['gender']=='female'
    job_id = before['report_jobs'][-1]['job_id']
    polled = client.get('/api/v1/selfit/report-jobs/'+job_id).json()['job']['report']
    assert polled['templateId']=='mute' and polled['gender']=='female'
    assert all(x['gender']!='male' for x in client.get('/selfit/try-on/report-outfits/home').json()['outfits'])
    after = onboarding._load_store()
    assert before['reports']==after['reports']
    assert before['user_photos']==after['user_photos']
    assert client.patch('/api/v1/selfit/me/gender', headers={'If-Match':str(profile['genderRevision'])}, json={'gender':'male'}).status_code==409
    assert client.get('/closet/preferences').json()['gender']=='female'
    assert client.post('/api/v1/selfit/sessions', json={'onboardingMode':'retest'}).json()['session']['gender']=='female'


def test_missing_male_report_has_usable_same_gender_home(journey, monkeypatch):
    client, url, _, _ = journey
    client.patch(url+'/gender', json={'gender':'male'})
    saved = make_report(client, url, monkeypatch, 'LOOP')
    assert saved['data']['recommendationStatus']=='pending_gender_content'
    assert saved['data']['outfits']==[]
    response = client.get('/selfit/try-on/report-outfits/home')
    assert response.status_code==200
    data = response.json()
    assert data['source']=='gender_library' and data['persona']=='loop' and data['notice']
    assert len(data['outfits'])==4 and all(x['gender']=='male' for x in data['outfits'])


def test_legacy_choice_survives_expiry_and_anonymous_cannot_change_account(journey):
    client, url, user_id, token = journey
    data=onboarding._load_store()
    data['sessions'][0].update(gender='male',expires_at='2000-01-01T00:00:00Z')
    data['user_profiles']=[]
    onboarding._write_store(data)
    assert auth.resolve_token(token)['gender']=='male'
    onboarding._write_store(onboarding._prune_store(onboarding._load_store()))
    assert not onboarding._load_store()['sessions']
    assert declared_profile(onboarding._load_store(),user_id)['gender']=='male'
    assert TestClient(app).patch('/api/v1/selfit/me/gender',json={'gender':'female'}).status_code==401
    assert client.patch('/api/v1/selfit/me/gender',headers={'If-Match':'0'},json={'gender':'other'}).status_code==422
    assert auth.resolve_token(token)['gender']=='male'


def test_session_conflict_and_idempotency_do_not_revert_account(journey):
    client, url, _, token=journey
    original=client.get(url).json()['session']['revision']
    header={'If-Match':str(original),'X-Idempotency-Key':'select-male-once'}
    assert client.patch(url+'/gender',headers=header,json={'gender':'male'}).status_code==200
    assert client.patch(url+'/gender',headers={'If-Match':str(original)},json={'gender':'female'}).status_code==409
    profile=client.get('/api/v1/selfit/me/profile').json()['profile']
    assert client.patch('/api/v1/selfit/me/gender',headers={'If-Match':str(profile['genderRevision'])},json={'gender':'female'}).status_code==200
    assert client.patch(url+'/gender',headers=header,json={'gender':'male'}).status_code==200
    assert auth.resolve_token(token)['gender']=='female'

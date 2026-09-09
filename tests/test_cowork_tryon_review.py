"""Audit safety checks; no local server or production database is started."""
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1] / 'cowork/tryon-review'
pytest.importorskip('psycopg')
if not (PROJECT / 'seeds/catalog.json').exists():
    pytest.skip('Run scripts/export_tryon_review_catalog.py first', allow_module_level=True)
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location('cowork_review_app', PROJECT / 'app.py')
review_app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = review_app
spec.loader.exec_module(review_app)
sys.path.pop(0)
client = TestClient(review_app.app)
SSO = json.dumps({'userId':'review-test','username':'审核测试','email':'review-test@example.test'})


def test_catalog_matches_complete_batch_and_adjusted_provenance():
    catalog = review_app.CATALOG
    assert catalog['counts'] == dict(outfits=80,expected=240,available=239,missing=1,adjusted=3)
    assert len(review_app.RESULTS) == 240
    assert sum(r['originalStatus']=='failed_quality' for r in review_app.RESULTS.values()) == 37
    assert all(not r['originalRequestEquivalent'] for r in review_app.RESULTS.values() if r['adjusted'])
    assert len({m['image'] for m in catalog['models']}) == 3
    assert all(len({r['modelId'] for r in o['results']})==3 for o in catalog['outfits'])


@pytest.mark.parametrize('path',['/','/api/catalog','/api/export','/whoami'])
def test_business_reads_require_sso(path):
    assert client.get(path).status_code == 401


def test_sso_handles_unicode_and_rejects_missing_identity():
    header=json.dumps({'userId':'123','username':'须隐'},ensure_ascii=False).encode('utf-8').decode('latin1')
    assert review_app._parse_sso_user(header)['name']=='须隐'
    for raw in [None,'{}','[]','not-json','{"email":"name@example.test"}']:
        assert review_app._parse_sso_user(raw) is None


def test_missing_image_cannot_be_approved_or_write_database(monkeypatch):
    no_db=Mock(side_effect=AssertionError('must reject before opening DB'))
    monkeypatch.setattr(review_app,'connect',no_db)
    missing=next(r for r in review_app.RESULTS.values() if not r['image'])
    response=client.put('/api/review',headers={'Decrypted-Userinfo':SSO},json={
        'reviewKey':missing['reviewKey'],'decision':'approved','note':'','revision':0})
    assert response.status_code==422
    no_db.assert_not_called()


def test_redo_requires_actionable_note():
    key=next(iter(review_app.RESULTS))
    response=client.put('/api/review',headers={'Decrypted-Userinfo':SSO},json={
        'reviewKey':key,'decision':'redo','note':'   ','revision':0})
    assert response.status_code==422


def test_stale_revision_cannot_overwrite_another_reviewer(monkeypatch):
    conn=Mock()
    conn.execute.return_value.fetchone.return_value={'revision':3}
    @contextmanager
    def db(): yield conn
    monkeypatch.setattr(review_app,'connect',db)
    key=next(r['reviewKey'] for r in review_app.RESULTS.values() if r['image'])
    response=client.put('/api/review',headers={'Decrypted-Userinfo':SSO},json={
        'reviewKey':key,'decision':'approved','note':'','revision':2})
    assert response.status_code==409
    assert not any(call.args[0].lstrip().startswith('UPDATE tryon_reviews') for call in conn.execute.call_args_list)


def test_catalog_returns_existing_urls_for_direct_images(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = []
    @contextmanager
    def db(): yield conn
    monkeypatch.setattr(review_app, 'connect', db)
    payload = client.get('/api/catalog', headers={'Decrypted-Userinfo': SSO}).json()
    assert payload['assets'] == review_app.CATALOG['assets']
    assert all(entry['url'].startswith(('https://', 'http://')) for entry in payload['assets'].values())
    assert client.get('/api/media/unknown', headers={'Decrypted-Userinfo': SSO}).status_code == 404

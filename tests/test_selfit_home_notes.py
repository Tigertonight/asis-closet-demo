"""The normal mirror resolves four notes using only the signed-in account."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import selfit_onboarding as onboarding, selfit_report_outfits as outfits
from app.auth import get_current_user
from app.material_assets import MaterialRegistry

ENDPOINT = '/selfit/try-on/report-outfits/home'


def saved_report(user='viewer', persona='flou', when='2026-09-11', **data):
    return {'user_id': user, 'report_id': f'{user}-{when}', 'created_at': when,
            'data': {'typeId': persona, **data}}


@pytest.fixture
def home(monkeypatch):
    store = {'reports': []}
    user = {'user_id': 'viewer', 'gender': 'female'}
    monkeypatch.setattr(onboarding, '_load_store', lambda: store)
    monkeypatch.setattr(MaterialRegistry, 'get', lambda *_: {'url': '/static/fixture.png'})
    app = FastAPI(); app.include_router(outfits.router)
    client = TestClient(app)
    assert client.get(ENDPOINT).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: user
    return client, store, user


def test_untested_account_gets_four_random_distinct_notes_and_keeps_selection(home, monkeypatch):
    client, store, user = home
    store['reports'] = [saved_report('someone-else'), saved_report(persona='')]
    monkeypatch.setattr(outfits.random, 'sample', lambda rows, count: rows[:count])
    result = client.get(ENDPOINT, params={'persona': 'flou', 'user_id': 'someone-else'}).json()
    assert result['source'] == 'random'
    rows = result['outfits']
    assert len(rows) == len({row['source_asset_id'] for row in rows}) == 4
    assert all(row['items'] and row['gender'] != 'male' for row in rows)
    monkeypatch.setattr(outfits.random, 'sample', lambda rows, count: rows[-count:])
    refreshed = client.get(ENDPOINT).json()['outfits']
    assert {row['outfit_id'] for row in rows} != {row['outfit_id'] for row in refreshed}
    pinned = client.get(ENDPOINT, params={'selected_outfit_id': rows[2]['outfit_id']}).json()['outfits']
    assert len(pinned) == 4 and pinned[0] == rows[2]
    user['gender'] = 'male'
    male = client.get(ENDPOINT).json()['outfits']
    assert len(male) == 4 and all(row['gender'] == 'male' for row in male)


def test_latest_own_report_keeps_four_notes_and_order_without_random_substitution(home, monkeypatch):
    client, store, _ = home
    ids = ['outfits-04', 'outfits-02', 'outfits-01', 'outfits-03']
    store['reports'] = [saved_report(persona='ease', when='2026-09-09'),
                        saved_report(outfits=[{'id': key} for key in ids]),
                        saved_report('someone-else', persona='void', when='2026-09-12'),
                        saved_report(persona='', when='2026-09-13')]
    monkeypatch.setattr(outfits.random, 'sample', lambda *_: pytest.fail('a tested account must not sample'))
    unrelated = outfits.report_outfits('void', ['outfits-01'])['outfits'][0]['outfit_id']
    response = client.get(ENDPOINT, params={'selected_outfit_id': unrelated})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    result = response.json()
    assert result['source'] == 'report' and result['persona'] == 'flou'
    assert [row['report_note']['id'].split(':')[-1] for row in result['outfits']] == ids
    assert all(row['template_id'] == 'flou' and row['outfit_id'] != unrelated for row in result['outfits'])
    assert client.get(ENDPOINT).json()['outfits'] == result['outfits']


@pytest.mark.parametrize('persona,template,gender', [('void','void-curvy','female'),('ease','ease-male','male')])
def test_report_template_variant_is_preserved(home, persona, template, gender):
    client, store, user = home
    user['gender'] = gender
    store['reports'] = [saved_report(persona=persona, templateId=template, gender=gender)]
    response = client.get(ENDPOINT)
    assert response.status_code == 200
    rows = response.json()['outfits']
    assert len(rows) == 4 and all(row['template_id'] == template for row in rows)


def test_legacy_report_without_template_uses_persona_and_gender(home):
    client, store, user = home
    user['gender'] = 'male'
    store['reports'] = [saved_report(persona='EASE')]
    result = client.get(ENDPOINT).json()
    assert result['persona'] == 'ease' and result['template_id'] == 'ease-male'
    assert len(result['outfits']) == 4


def test_report_completion_and_retest_replace_random_or_previous_persona_on_next_entry(home):
    client, store, _ = home
    assert client.get(ENDPOINT).json()['source'] == 'random'
    store['reports'].append(saved_report())
    assert client.get(ENDPOINT).json()['persona'] == 'flou'
    store['reports'].append(saved_report(persona='void', when='2026-09-12'))
    changed = client.get(ENDPOINT).json()
    assert changed['persona'] == 'void' and len(changed['outfits']) == 4


def test_missing_report_template_or_delivery_never_falls_back_to_random(home, monkeypatch):
    client, store, _ = home
    monkeypatch.setattr(outfits.random, 'sample', lambda *_: pytest.fail('must not show unrelated random notes'))
    store['reports'] = [saved_report(templateId='flou-male', gender='male')]
    assert client.get(ENDPOINT).status_code == 503
    store['reports'] = [saved_report()]
    monkeypatch.setattr(outfits, 'delivery_looks', lambda: [])
    assert client.get(ENDPOINT).status_code == 503


def test_store_read_error_is_retryable_instead_of_treating_account_as_untested(home, monkeypatch):
    client, _, _ = home
    def unavailable(): raise OSError('test-only read failure')
    monkeypatch.setattr(onboarding, '_load_store', unavailable)
    monkeypatch.setattr(outfits.random, 'sample', lambda *_: pytest.fail('must not sample after store error'))
    assert client.get(ENDPOINT).status_code == 503

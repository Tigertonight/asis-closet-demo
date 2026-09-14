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
def home(monkeypatch, tmp_path):
    store = {'reports': []}
    user = {'user_id': 'viewer', 'gender': 'female'}
    monkeypatch.setattr(onboarding, '_load_store', lambda: store)
    monkeypatch.setattr(outfits, '_home_notes_path', lambda uid: tmp_path / uid / 'home.json')
    monkeypatch.setattr(MaterialRegistry, 'get', lambda *_: {'url': '/static/fixture.png'})
    app = FastAPI(); app.include_router(outfits.router)
    client = TestClient(app)
    assert client.get(ENDPOINT).status_code == 401
    assert client.post(ENDPOINT + '/refresh').status_code == 401
    app.dependency_overrides[get_current_user] = lambda: user
    return client, store, user


def test_untested_account_keeps_four_notes_until_explicit_refresh(home, monkeypatch):
    client, store, user = home
    store['reports'] = [saved_report('someone-else'), saved_report(persona='')]
    monkeypatch.setattr(outfits.random, 'sample', lambda rows, count: rows[:count])
    result = client.get(ENDPOINT, params={'persona': 'flou', 'user_id': 'someone-else'}).json()
    assert result['source'] == 'random'
    rows = result['outfits']
    assert len(rows) == len({row['source_asset_id'] for row in rows}) == 4
    assert all(row['items'] and row['gender'] != 'male' for row in rows)
    monkeypatch.setattr(outfits.random, 'sample', lambda rows, count: rows[-count:])
    assert client.get(ENDPOINT).json()['outfits'] == rows
    refreshed = client.post(ENDPOINT + '/refresh').json()['outfits']
    assert {row['outfit_id'] for row in rows} != {row['outfit_id'] for row in refreshed}
    assert not {row['source_asset_id'] for row in rows} & {row['source_asset_id'] for row in refreshed}
    pinned = client.get(ENDPOINT, params={'selected_outfit_id': rows[2]['outfit_id']}).json()['outfits']
    assert pinned == refreshed, 'selection must not displace recommendations'
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
    store['reports'] = [saved_report(templateId='flou-missing', gender='female')]
    assert client.get(ENDPOINT).status_code == 503
    store['reports'] = [saved_report()]
    monkeypatch.setattr(outfits, 'delivery_looks', lambda: [])
    assert client.get(ENDPOINT).status_code == 503


def test_tested_refresh_explores_without_changing_report_and_persists(home):
    import copy
    client, store, _ = home
    store['reports'] = [saved_report()]
    original = copy.deepcopy(store)
    initial = client.get(ENDPOINT).json()
    response = client.post(ENDPOINT + '/refresh')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    explored = response.json()
    assert explored['source'] == 'explore'
    assert not {row['source_asset_id'] for row in initial['outfits']} & {row['source_asset_id'] for row in explored['outfits']}
    assert any(row['report_note']['persona'] != 'flou' for row in explored['outfits'])
    assert client.get(ENDPOINT).json()['outfits'] == explored['outfits']
    assert store == original


def test_gender_and_retest_reset_exploration_and_never_mix_gender(home):
    client, store, user = home
    store['reports'] = [saved_report(persona='ease')]
    client.post(ENDPOINT + '/refresh')
    user['gender'] = 'male'
    rows = client.get(ENDPOINT).json()['outfits']
    assert all(row['template_id'] == 'ease-male' for row in rows)
    for _ in range(6):
        rows = client.post(ENDPOINT + '/refresh').json()['outfits']
        assert len(rows) == 4 and all(row['gender'] == 'male' for row in rows)
    store['reports'].append(saved_report(persona='wabi', when='2026-09-14'))
    assert all(row['template_id'] == 'wabi-male' for row in client.get(ENDPOINT).json()['outfits'])


def test_refresh_cycles_without_repeats_and_accounts_are_isolated(home):
    client, _, user = home
    user['gender'] = 'male'
    first = client.get(ENDPOINT).json()['outfits']
    seen = {row['source_asset_id'] for row in first}
    previous = seen.copy()
    for _ in range(3):
        rows = client.post(ENDPOINT + '/refresh').json()['outfits']
        ids = {row['source_asset_id'] for row in rows}
        assert len(ids) == 4 and not seen & ids
        seen |= ids
        previous = ids
    assert len(seen) == 16
    rows = client.post(ENDPOINT + '/refresh').json()['outfits']
    assert not previous & {row['source_asset_id'] for row in rows}
    user['user_id'] = 'another-viewer'
    client.post(ENDPOINT + '/refresh')
    user['user_id'] = 'viewer'
    assert client.get(ENDPOINT).json()['outfits'] == rows


def test_failed_refresh_preserves_persisted_batch(home, monkeypatch):
    client, _, user = home
    rows = client.get(ENDPOINT).json()['outfits']
    path = outfits._home_notes_path(user['user_id'])
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(outfits, 'delivery_looks', lambda: [])
        assert client.post(ENDPOINT + '/refresh').status_code == 503
    assert path.read_bytes() == before
    assert client.get(ENDPOINT).json()['outfits'] == rows


def test_saved_notes_only_store_identifiers_and_resolve_current_assets(home):
    client, _, user = home
    client.get(ENDPOINT)
    stored = outfits._home_notes_path(user['user_id']).read_text()
    assert 'image_url' not in stored and 'cutout' not in stored
    assert 'access_token' not in stored and '/static/' not in stored


def test_gender_roundtrip_resets_even_without_visiting_mirror_between_changes(home):
    client, store, _ = home
    store['reports'] = [saved_report()]
    store['user_profiles'] = [{'user_id':'viewer', 'gender':'female', 'gender_revision':1}]
    client.post(ENDPOINT + '/refresh')
    store['user_profiles'][0]['gender_revision'] = 3
    result = client.get(ENDPOINT).json()
    assert result['source'] == 'report' and result['persona'] == 'flou'


def test_store_read_error_is_retryable_instead_of_treating_account_as_untested(home, monkeypatch):
    client, _, _ = home
    def unavailable(): raise OSError('test-only read failure')
    monkeypatch.setattr(onboarding, '_load_store', unavailable)
    monkeypatch.setattr(outfits.random, 'sample', lambda *_: pytest.fail('must not sample after store error'))
    assert client.get(ENDPOINT).status_code == 503

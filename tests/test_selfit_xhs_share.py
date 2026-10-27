from concurrent.futures import ThreadPoolExecutor
import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import selfit_xhs_share as xhs, selfit_mirror_photos as photos
from app.main import app


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv('SELFIT_XHS_APP_KEY', 'test-key')
    monkeypatch.setenv('SELFIT_XHS_APP_SECRET', 'test-secret')
    monkeypatch.setenv('SELFIT_XHS_CACHE_DIR', str(tmp_path / 'xhs'))
    calls = []
    def request(key, secret):
        calls.append((key, secret))
        return 'private-test-token', int(time.time() * 1000) + 86400000
    monkeypatch.setattr(xhs, '_request_token', request)
    return calls


def test_matches_official_java_signature_example():
    assert xhs.signature('123', 'nonce', '1692102691696', 'test') == '16c900bfce9d55a78406a8d5a0be0b04cd4881bde8ade0b7bc9ae7ea2d32c506'


def test_concurrent_signatures_share_one_persistent_token(configured):
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(lambda _: xhs.verify_config(), range(5)))
    assert len(configured) == 1
    assert len({r['verifyConfig']['nonce'] for r in results}) == 5
    for result in results:
        config = result['verifyConfig']
        assert config['signature'] == xhs.signature(config['appKey'], config['nonce'], config['timestamp'], 'private-test-token')
        assert 0 < result['expiresAt'] - int(time.time() * 1000) <= 180000
        assert 'private-test-token' not in json.dumps(result)
        assert 'test-secret' not in json.dumps(result)
    assert (xhs._directory() / 'token.json').stat().st_mode & 0o777 == 0o600
    # A later request reads the persisted token, rather than revoking it upstream.
    xhs.verify_config()
    assert len(configured) == 1


def test_refresh_boundary_and_credential_rotation(configured, monkeypatch):
    xhs.verify_config()
    path = xhs._directory() / 'token.json'
    cache = json.loads(path.read_text())
    cache['expiresAt'] = int(time.time() * 1000) + xhs.REFRESH_MARGIN_MS - 1000
    path.write_text(json.dumps(cache))
    xhs.verify_config()
    assert len(configured) == 2
    monkeypatch.setenv('SELFIT_XHS_APP_SECRET', 'rotated-secret')
    xhs.verify_config()
    assert configured[-1] == ('test-key', 'rotated-secret')


def test_provider_failure_has_cooldown_and_does_not_echo_secrets(configured, monkeypatch, caplog):
    calls = []
    def fail(*args):
        calls.append(1)
        raise httpx.ReadTimeout('test-secret in unsafe provider exception')
    monkeypatch.setattr(xhs, '_request_token', fail)
    for _ in range(2):
        with pytest.raises(xhs.ShareUnavailable) as error:
            xhs.verify_config()
        assert 'test-secret' not in str(error.value)
    assert len(calls) == 1
    assert 'test-secret' not in caplog.text


@pytest.fixture
def receipt(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(photos, 'PHOTO_DIR', tmp_path / 'photos')
    monkeypatch.setenv('SELFIT_PUBLIC_BASE_URL', 'https://selfit.com.cn')
    def image(size, fmt):
        out = io.BytesIO(); Image.new('RGB', size, 'white').save(out, fmt); return out.getvalue()
    secret = 'a' * 64
    record = photos._save(image((50, 100), 'JPEG'), image((900, 1200), 'PNG'), json.dumps({'template': 'woken-stamp'}), secret)
    with TestClient(app) as client:
        yield client, record, {'Authorization': 'Bearer ' + secret}


def test_share_requires_receipt_and_expires_before_token_refresh(receipt, configured):
    client, record, headers = receipt
    base = f"/api/v1/selfit/mirror/photos/{record['id']}"
    assert client.get(base + '/xhs-share').status_code == 404
    assert not configured
    response = client.get(base + '/xhs-share', headers={**headers, 'Host': 'attacker.invalid'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    payload = response.json()
    assert set(payload['shareInfo']) == {'type', 'images'}
    image = payload['shareInfo']['images'][0]
    assert image.startswith('https://selfit.com.cn/api/v1/') and '/files/print.png?' in image
    assert 'download=0' in image
    assert client.get(image).headers['content-type'] == 'image/png'
    assert all(s not in response.text for s in ('a' * 64, 'private-test-token', 'test-secret', 'original', 'scene.png'))
    assert len(configured) == 1
    with photos._database() as db:
        db.execute('UPDATE photos SET expires=?', (time.time() - 1,))
    assert client.get(base + '/xhs-share', headers=headers).status_code == 410
    assert len(configured) == 1


def test_missing_configuration_hides_action_and_does_not_call_provider(receipt, configured, monkeypatch):
    client, record, headers = receipt
    monkeypatch.delenv('SELFIT_XHS_APP_SECRET')
    base = f"/api/v1/selfit/mirror/photos/{record['id']}"
    assert client.get(base + '/info', headers=headers).json()['xhsShareEnabled'] is False
    assert client.get(base + '/xhs-share', headers=headers).status_code == 503
    assert not configured


def test_other_photo_editions_do_not_show_stamp_share(receipt, configured):
    client, record, headers = receipt
    with photos._database() as db:
        db.execute('UPDATE photos SET settings=? WHERE id=?', ('{}', record['id']))
    base = f"/api/v1/selfit/mirror/photos/{record['id']}"
    assert client.get(base + '/info', headers=headers).json()['xhsShareEnabled'] is False
    assert client.get(base + '/xhs-share', headers=headers).status_code == 404
    assert not configured


def test_invalid_public_origin_and_missing_print_fail_before_signing(receipt, configured, monkeypatch):
    client, record, headers = receipt
    url = f"/api/v1/selfit/mirror/photos/{record['id']}/xhs-share"
    monkeypatch.setenv('SELFIT_PUBLIC_BASE_URL', 'http://selfit.com.cn')
    assert client.get(url, headers=headers).status_code == 503
    monkeypatch.setenv('SELFIT_PUBLIC_BASE_URL', 'https://selfit.com.cn')
    photos._store().local_path(f"mirror-photos/{record['id']}/print.png").unlink()
    assert client.get(url, headers=headers).status_code == 503
    assert not configured


def test_sdk_only_loaded_on_separate_secret_free_page(receipt):
    client, _, _ = receipt
    receipt_page = client.get('/selfit/photo')
    share_page = client.get('/selfit/photo/share')
    assert 'xhscdn' not in receipt_page.text
    assert share_page.status_code == 200
    assert share_page.headers['referrer-policy'] == 'no-referrer'

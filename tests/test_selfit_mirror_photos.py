from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import sqlite3
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app import selfit_mirror_photos as photos, ops

SETTINGS = dict(template='stamp', stampYear='2019-2020', effect='retro', palette='original', background='#e8dfd5', intensity=45, zoom=1, x=0, y=0)
SECRET = 'c' * 64


def photo(size, color, fmt):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, fmt)
    return out.getvalue()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(photos, 'PHOTO_DIR', tmp_path / 'photos')
    monkeypatch.setenv('SELFIT_ASSET_STORE', 'local')
    monkeypatch.setenv('SELFIT_PUBLIC_BASE_URL', 'https://selfit.com.cn')
    with TestClient(app) as client:
        yield client


def save(client, secret=SECRET, **overrides):
    original = overrides.pop('original', photo((400, 700), '#5e7f92', 'JPEG'))
    final = overrides.pop('final', photo((1080, 1440), '#e8dfd5', 'PNG'))
    return client.post('/api/v1/selfit/mirror/photos', headers={'Idempotency-Key': secret},
        data={'settings': json.dumps({**SETTINGS, **overrides})},
        files={'original': ('raw.jpg', original, 'image/jpeg'), 'final': ('final.png', final, 'image/png')})


def retrieve(client, photo_id, variant, secret=SECRET):
    return client.get(f'/api/v1/selfit/mirror/photos/{photo_id}/{variant}', headers={'Authorization': 'Bearer ' + secret})


def test_composed_photo_roundtrip_and_private_original(client):
    original = photo((400, 700), '#5e7f92', 'JPEG')
    final = photo((1080, 1440), '#e8dfd5', 'PNG')
    response = save(client, original=original, final=final)
    assert response.status_code == 201, response.text
    payload = response.json(); photo_id = payload['photoId']
    with photos._database() as db:
        stored = db.execute('SELECT settings FROM photos WHERE id=?', (photo_id,)).fetchone()
        assert json.loads(stored[0])['stampYear'] == '2019-2020'
    assert 86000 < payload['expiresAt'] / 1000 - time.time() <= 86400
    preview = retrieve(client, photo_id, 'preview')
    assert preview.headers['content-type'] == 'image/webp'
    assert Image.open(io.BytesIO(preview.content)).size == (720, 960)
    download = retrieve(client, photo_id, 'download')
    assert download.content == final
    assert download.headers['cache-control'] == 'no-store'
    assert 'attachment' in download.headers['content-disposition']
    path = photos.PHOTO_DIR / 'assets' / 'mirror-photos' / photo_id
    assert (path / 'original.jpg').read_bytes() == original
    assert retrieve(client, photo_id, 'original').status_code == 404
    assert client.get(f'/api/v1/selfit/mirror/photos/{photo_id}/preview').status_code == 404
    assert retrieve(client, photo_id, 'preview', 'd' * 64).status_code == 404
    qr = retrieve(client, photo_id, 'qr')
    img = cv2.imdecode(np.frombuffer(qr.content, np.uint8), cv2.IMREAD_COLOR)
    url = cv2.QRCodeDetector().detectAndDecode(img)[0]
    assert url == f'https://selfit.com.cn/selfit/photo#{photo_id}.{SECRET}'
    assert SECRET not in (photos.PHOTO_DIR / 'photos.sqlite3').read_bytes().decode('latin1')
    page = client.get('/selfit/photo')
    assert page.status_code == 200
    assert page.headers['referrer-policy'] == 'no-referrer'


def test_lost_response_retry_is_idempotent_and_edits_conflict(client):
    first, second = save(client), save(client)
    assert first.json() == second.json()
    assert save(client, intensity=65).status_code == 409
    with photos._database() as db:
        assert db.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 1


def test_simultaneous_retries_share_one_record(client):
    original = photo((400, 700), '#5e7f92', 'JPEG'); final = photo((1080, 1440), '#e8dfd5', 'PNG')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: photos._save(original, final, json.dumps(SETTINGS), SECRET), range(2)))
    assert results[0]['id'] == results[1]['id']
    with photos._database() as db:
        assert db.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 1


@pytest.mark.parametrize('variant', ['info', 'preview', 'download', 'qr'])
def test_expiry_checked_on_every_read(client, variant):
    photo_id = save(client).json()['photoId']
    with photos._database() as db:
        db.execute('UPDATE photos SET expires=?', (time.time() - 1,))
    expired = retrieve(client, photo_id, variant)
    assert expired.status_code == 410
    assert '领取链接已过期' in expired.json()['error']['message']
    assert save(client).status_code == 410


@pytest.mark.parametrize('change,status', [
    ({'original': b'bad jpeg'}, 415),
    ({'original': b'x' * (photos.MAX_BYTES + 1)}, 413),
    ({'final': photo((540, 720), 'white', 'PNG')}, 422),
    ({'final': photo((1080, 1440), 'white', 'JPEG')}, 422),
    ({'original': photo((4100, 4100), 'white', 'JPEG')}, 413),
    ({'intensity': float('nan')}, 400), ({'zoom': 0}, 400), ({'template': 'unknown'}, 400),
    ({'stampYear': None}, 400), ({'stampYear': '2026-2027'}, 400),
    ({'stampYear': True}, 400), ({'stampYear': ['2019-2020']}, 400),
])
def test_invalid_inputs_create_no_record(client, change, status):
    assert save(client, **change).status_code == status
    with photos._database() as db:
        assert db.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 0


def test_stamp_requires_an_explicit_year():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        photos._settings(json.dumps({k: v for k, v in SETTINGS.items() if k != 'stampYear'}))
    assert error.value.status_code == 400
    for year in range(2016, 2026):
        value = f'{year}-{year + 1}'
        assert json.loads(photos._settings(json.dumps({**SETTINGS, 'stampYear': value})))['stampYear'] == value


def test_missing_photo_preserves_retrieval_error_not_upload_error(client):
    response = retrieve(client, 'mp_' + '0' * 32, 'info')
    assert response.status_code == 404
    assert response.json()['error']['message'] == '照片不存在或领取链接不完整。'


def test_image_work_has_bounded_admission(client, monkeypatch):
    class Full:
        def acquire_nowait(self):
            import anyio
            raise anyio.WouldBlock
    monkeypatch.setattr(photos, 'photo_admission', lambda: Full())
    response = save(client)
    assert response.status_code == 503
    assert response.headers['retry-after'] == '3'


def test_photo_reads_dont_consume_upload_limit():
    assert ops._matching_rule('/api/v1/selfit/mirror/photos', 'POST').name == 'mirror_upload'
    assert ops._matching_rule('/api/v1/selfit/mirror/photos/mp_123/qr', 'GET').name == 'mirror_handoff'


def test_admin_keepsake_listing_download_expiry_and_soft_hide(client, monkeypatch, tmp_path):
    from app import auth, selfit_admin_submissions as admin, selfit_mirror_handoff as handoff
    monkeypatch.setattr(auth, 'AUTH_STORE_PATH', tmp_path / 'auth.json')
    monkeypatch.setattr(auth, 'ADMIN_PASSWORD_PATH', tmp_path / 'admin-password.json')
    monkeypatch.setattr(admin, 'HIDDEN_STORE_PATH', tmp_path / 'hidden.json')
    monkeypatch.setattr(handoff, 'HANDOFF_STORE_PATH', tmp_path / 'handoffs.json')
    photo_id = save(client).json()['photoId']
    url = f'/admin/api/mirror-keepsakes/{photo_id}/print?download=1'
    assert client.get(url).status_code in {401, 403}
    app.dependency_overrides[auth.get_admin_user] = lambda: {'user_id': 'test-admin'}
    try:
        with photos._database() as db:
            db.execute('UPDATE photos SET expires=?', (time.time() - 1,))
        captures = client.get('/admin/api/mirror-captures').json()['captures']
        row = next(row for row in captures if row['handoffId'] == photo_id)
        assert row['status'] == 'keepsake'
        assert row['retouched']['label'] == '模板成片'
        download = client.get(row['retouched']['downloadUrl'])
        assert Image.open(io.BytesIO(download.content)).size == (1080, 1440)
        assert download.headers['content-type'] == 'image/png'
        assert client.post(f'/admin/api/mirror-captures/{photo_id}/hide').status_code == 200
        assert photo_id not in [r['handoffId'] for r in client.get('/admin/api/mirror-captures').json()['captures']]
        assert client.get(url).status_code == 200
    finally:
        app.dependency_overrides.pop(auth.get_admin_user, None)

STAMP_SETTINGS = dict(template='woken-stamp', stampYear='2025-2026', effect='fine-halftone', palette='original', background='#111214', customInk='#d91f32', intensity=80, zoom=1, x=0, y=0)


def save_stamp(client, *, scene=True, final_size=(900, 1200), **settings):
    files = {'original': ('raw.jpg', photo((400, 700), '#5e7f92', 'JPEG'), 'image/jpeg'),
             'final': ('stamp.png', photo(final_size, '#174fe4', 'PNG'), 'image/png')}
    if scene:
        files['scene'] = ('scene.png', photo((900, 1200), '#dddddd', 'PNG'), 'image/png')
    return client.post('/api/v1/selfit/mirror/photos', headers={'Idempotency-Key': SECRET},
                       data={'settings': json.dumps({**STAMP_SETTINGS, **settings})}, files=files)


def test_older_stamp_two_outputs_remain_readable_in_private_storage(client, monkeypatch):
    # A deployment's object-storage setting must not publish these private photos.
    monkeypatch.setenv('SELFIT_ASSET_STORE', 's3')
    saved = save_stamp(client)
    assert saved.status_code == 201, saved.text
    photo_id = saved.json()['photoId']
    metadata = retrieve(client, photo_id, 'info').json()
    assert (metadata['width'], metadata['height'], metadata['hasScene'], metadata['edition']) == (900, 1200, True, 'woken')
    for variant in ['preview', 'scene-preview', 'download', 'scene-download']:
        response = retrieve(client, photo_id, variant)
        assert response.status_code == 200
        assert Image.open(io.BytesIO(response.content)).size == ((720, 960) if 'preview' in variant else (900, 1200))
        assert client.get(f'/api/v1/selfit/mirror/photos/{photo_id}/{variant}').status_code == 404
    assert save_stamp(client).json() == saved.json()
    with photos._database() as db:
        db.execute('UPDATE photos SET expires=?', (time.time() - 1,))
    for variant in ['scene-preview', 'scene-download']:
        assert retrieve(client, photo_id, variant).status_code == 410
    rows = photos.admin_capture_rows()
    assert rows[0]['scene']['label'] == '出片机展示图'
    assert photos.admin_photo(photo_id, 'scene', True, {}).media_type == 'image/png'
    assert client.get(f'/admin/api/mirror-keepsakes/{photo_id}/scene').status_code in (401, 403)


@pytest.mark.parametrize('change,status', [
    ({'final_size': (1080, 1440)}, 422),
    ({'stampYear': '2026-2027'}, 400), ({'effect': 'unknown'}, 400),
    ({'palette': []}, 400), ({'intensity': True}, 400), ({'x': float('inf')}, 400),
    ({'background': 'red'}, 400), ({'customInk': 'transparent'}, 400),
])
def test_invalid_stamp_creates_no_partial_photos(client, change, status):
    assert save_stamp(client, **change).status_code == status
    assert not (photos.PHOTO_DIR / 'assets').exists()


def test_transparent_stamp_preview_preserves_alpha():
    buffer = io.BytesIO()
    Image.new('RGBA', (900, 1200), (255, 255, 255, 0)).save(buffer, 'PNG')
    preview = photos._check_image(buffer.getvalue(), final=True, size=(900, 1200))
    with Image.open(io.BytesIO(preview)) as image:
        assert image.getpixel((0, 0))[3] == 0


def test_stamp_page_is_separate_and_local_assets_resolve(client):
    import re
    for route in ['/selfit/stamp', '/selfit/stamp/']:
        page = client.get(route)
        assert page.status_code == 200
        assert 'WOKEN DAY 十周年照相馆' in page.text
        for url in re.findall(r'(?:src|href)="(/static/[^\"]+)"', page.text):
            assert client.get(url).status_code == 200, url
    for year in range(1, 11):
        assert client.get(f'/static/selfit/stamp/assets/stamps/stamp-{year:02}-{2015+year}-{2016+year}.png').status_code == 200


def test_native_png_download_and_inline_urls_preserve_privacy(client):
    photo_id = save_stamp(client).json()['photoId']
    assert client.get(f'/api/v1/selfit/mirror/photos/{photo_id}/info').status_code == 404
    metadata = retrieve(client, photo_id, 'info').json()
    links = metadata['imageLinks']
    assert 590 < links['expiresAt'] / 1000 - time.time() <= photos.FILE_LINK_TTL
    assert SECRET not in json.dumps(links)
    for key, filename in [('print', 'WOKEN-DAY-STAMP.png'), ('scene', 'WOKEN-DAY-MACHINE.png')]:
        for action, disposition in [('view', 'inline'), ('download', 'attachment')]:
            url = links[key][action]
            assert url.startswith(f'/api/v1/selfit/mirror/photos/{photo_id}/files/')
            result = client.get(url)  # Native save has no Authorization header.
            assert result.status_code == 200
            assert result.headers['content-type'] == 'image/png'
            assert result.headers['content-disposition'] == f'{disposition}; filename="{filename}"'
            assert result.headers['cache-control'] == 'no-store'
            assert result.headers['referrer-policy'] == 'no-referrer'
            image = Image.open(io.BytesIO(result.content))
            assert image.format == 'PNG' and image.size == (900, 1200)
        assert client.get(links[key]['view']).content == client.get(links[key]['download']).content


def test_native_urls_cannot_change_photo_variant_expiry_or_disposition(client):
    from urllib.parse import urlsplit, parse_qs, urlencode
    photo_id = save_stamp(client).json()['photoId']
    url = retrieve(client, photo_id, 'info').json()['imageLinks']['print']['download']
    path = urlsplit(url).path
    params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert client.get(path).status_code == 404
    for field, value in [('signature', '0' * 64), ('signature', ''), ('expires', str(int(params['expires']) + 3600)), ('download', '0')]:
        assert client.get(path + '?' + urlencode({**params, field: value})).status_code == 404
    for name in ('original.jpg', 'original.png', 'scene.png', 'preview.webp'):
        assert client.get(url.replace('/print.png?', f'/{name}?')).status_code == 404
    other_id = save(client, secret='d' * 64).json()['photoId']
    assert client.get(url.replace(photo_id, other_id)).status_code == 404


def test_signed_png_head_has_get_headers_and_identical_authorization(client, monkeypatch):
    photo_id = save_stamp(client).json()['photoId']
    url = retrieve(client, photo_id, 'info').json()['imageLinks']['print']['view']
    get, head = client.get(url), client.head(url)
    assert head.status_code == 200 and head.content == b''
    for key in ['content-length', 'content-type', 'content-disposition', 'etag', 'cache-control']:
        assert head.headers[key] == get.headers[key]
    assert int(head.headers['content-length']) == len(get.content)
    assert client.head(url.split('?')[0]).status_code == 404
    assert client.head(url.replace('/print.png?', '/original.jpg?')).status_code == 404
    later = time.time() + photos.FILE_LINK_TTL + 2
    monkeypatch.setattr(photos.time, 'time', lambda: later)
    assert client.head(url).status_code == 410


def test_share_diagnostics_require_print_capability_and_log_no_secrets(client, caplog, monkeypatch):
    import logging
    photo_id = save_stamp(client).json()['photoId']
    url = retrieve(client, photo_id, 'info').json()['imageLinks']['print']['view']
    event_url = url.replace('/files/print.png', '/share-events')
    body = {'event': 'sdk_failed', 'flow': 'official-sdk', 'elapsed_ms': 123, 'error_code': 20003}
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        response = client.post(event_url, json=body, headers={'User-Agent': 'iPhone MicroMessenger/8.0 PRIVATE_UA'})
    assert response.status_code == 204
    row, = [json.loads(r.message) for r in caplog.records if r.message.startswith('{"event":"xhs_share_client"')]
    assert row['stage'] == 'sdk_failed' and row['error_code'] == 20003
    assert row['client_family'] == 'wechat' and row['client_platform'] == 'ios'
    assert len(row['photo_ref']) == 12
    for secret in [SECRET, photo_id, 'PRIVATE_UA', 'signature=', 'Bearer']:
        assert secret not in json.dumps(row)
    assert client.post(event_url.split('?')[0], json=body).status_code == 404
    assert client.post(event_url, json={**body, 'message': 'PRIVATE_ERROR'}).status_code == 422
    assert client.post(event_url, json={**body, 'event': 'untrusted-event'}).status_code == 422
    assert client.post(event_url, json={**body, 'error_code': 2**64}).status_code == 422
    later = time.time() + photos.FILE_LINK_TTL + 2
    monkeypatch.setattr(photos.time, 'time', lambda: later)
    assert client.post(event_url, json=body).status_code == 410


def test_browser_id_follows_images_and_share_events_without_granting_access(client, caplog, monkeypatch):
    import logging
    from urllib.parse import urlsplit, parse_qs
    photo_id = save_stamp(client).json()['photoId']
    base = f'/api/v1/selfit/mirror/photos/{photo_id}'
    client_id = 'mc_' + 'e' * 32
    headers = {'Authorization': 'Bearer ' + SECRET, 'X-Selfit-Client-Id': client_id}
    captured = []
    def prepare(image, page, agent):
        captured.append(image)
        return {'flow': 'official-sdk', 'shareInfo': {'type': 'normal', 'images': [image]},
                'expiresAt': int((time.time() + 180) * 1000)}
    monkeypatch.setattr(photos.selfit_xhs_share, 'prepare_share', prepare)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        info = client.get(base + '/info', headers=headers).json()
        url = info['imageLinks']['print']['view']
        assert parse_qs(urlsplit(url).query)['client_id'] == [client_id]
        assert client.get(url).status_code == 200
        assert client.head(url).status_code == 200
        assert client.get(base + '/xhs-share', headers=headers).status_code == 200
        assert parse_qs(urlsplit(captured[0]).query)['client_id'] == [client_id]
        assert client.post(url.replace('/files/print.png', '/share-events'), json={
            'event': 'preview_loaded', 'flow': 'official-sdk', 'elapsed_ms': 123}).status_code == 204
    rows = [json.loads(r.message) for r in caplog.records if r.message.startswith('{"event":')]
    linked = [r for r in rows if r.get('client_id') == client_id]
    assert any(r.get('client_id_source') == 'header' for r in linked)
    assert any(r.get('client_id_source') == 'photo_link' for r in linked)
    assert any(r.get('event') == 'xhs_share_client' for r in linked)
    assert SECRET not in json.dumps(linked) and 'signature=' not in json.dumps(linked)
    assert client.get(base + '/info', headers={'X-Selfit-Client-Id': client_id}).status_code == 404
    assert client.get(base + '/files/print.png?client_id=' + client_id).status_code == 404
    invalid = client.get(base + '/info', headers={**headers, 'X-Selfit-Client-Id': 'PRIVATE_BAD_ID'}).json()
    assert 'client_id=' not in invalid['imageLinks']['print']['view']


def test_share_diagnostics_are_limited_without_consuming_upload_or_image_allowance(client, monkeypatch):
    photo_id = save_stamp(client).json()['photoId']
    url = retrieve(client, photo_id, 'info').json()['imageLinks']['print']['view']
    monkeypatch.setattr(ops, '_limiter', ops.InMemoryRateLimiter())
    monkeypatch.setenv('SELFIT_DISABLE_RATE_LIMIT', 'false')
    monkeypatch.setenv('SELFIT_UPLOAD_RATE_LIMIT', '1')
    monkeypatch.setenv('SELFIT_MIRROR_SHARE_EVENT_RATE_LIMIT', '2')
    monkeypatch.setenv('SELFIT_MIRROR_HANDOFF_RATE_LIMIT', '1')
    event_url = url.replace('/files/print.png', '/share-events')
    body = {'event': 'sdk_ready', 'flow': 'official-sdk', 'elapsed_ms': 123}
    assert client.post(event_url, json=body).status_code == 204
    assert client.post(event_url, json=body).status_code == 204
    assert client.post(event_url, json=body).status_code == 429
    assert save_stamp(client).status_code == 201
    assert client.get(url).status_code == 200
    assert save_stamp(client).status_code == 429


def test_native_link_expiry_renewal_and_receipt_expiry(client, monkeypatch):
    now = time.time()
    photo_id = save_stamp(client).json()['photoId']
    links = retrieve(client, photo_id, 'info').json()['imageLinks']
    monkeypatch.setattr(photos.time, 'time', lambda: now + photos.FILE_LINK_TTL + 2)
    assert client.get(links['print']['download']).status_code == 410
    renewed = retrieve(client, photo_id, 'info').json()['imageLinks']
    assert renewed['print']['download'] != links['print']['download']
    assert client.get(renewed['print']['download']).status_code == 200
    with photos._database() as db:
        db.execute('UPDATE photos SET expires=?', (now + photos.FILE_LINK_TTL + 20,))
    bounded = retrieve(client, photo_id, 'info').json()['imageLinks']
    assert bounded['expiresAt'] == int(now + photos.FILE_LINK_TTL + 20) * 1000
    monkeypatch.setattr(photos.time, 'time', lambda: now + photos.FILE_LINK_TTL + 21)
    assert client.get(renewed['print']['download']).status_code == 410
    assert retrieve(client, photo_id, 'info').status_code == 410


def test_legacy_keepsake_has_single_native_png(client):
    photo_id = save(client).json()['photoId']
    links = retrieve(client, photo_id, 'info').json()['imageLinks']
    assert set(links) == {'expiresAt', 'print'}
    response = client.get(links['print']['download'])
    assert response.status_code == 200
    assert 'selfit-photo.png' in response.headers['content-disposition']
    assert Image.open(io.BytesIO(response.content)).size == (1080, 1440)


def test_stamp_without_scene_upload_download_and_admin_listing(client):
    saved = save_stamp(client, scene=False)
    assert saved.status_code == 201, saved.text
    photo_id = saved.json()['photoId']
    metadata = retrieve(client, photo_id, 'info').json()
    assert metadata['edition'] == 'woken' and metadata['hasScene'] is False
    assert set(metadata['imageLinks']) == {'expiresAt', 'print'}
    assert client.get(metadata['imageLinks']['print']['download']).status_code == 200
    assert retrieve(client, photo_id, 'qr').status_code == 200
    assert save_stamp(client, scene=False).json() == saved.json()
    for variant in ['scene-preview', 'scene-download']:
        assert retrieve(client, photo_id, variant).status_code == 404
    assert not (photos.PHOTO_DIR / 'assets' / 'mirror-photos' / photo_id / 'scene.png').exists()
    assert 'scene' not in photos.admin_capture_rows()[0]


@pytest.mark.parametrize('stamp', [True, False])
def test_share_qr_requests_fresh_share_on_scan_and_keeps_secret_in_fragment(client, stamp):
    from urllib.parse import urlsplit
    photo_id = (save_stamp(client, scene=False) if stamp else save(client)).json()['photoId']
    qr = retrieve(client, photo_id, 'qr?intent=xhs')
    assert qr.status_code == 200
    img = cv2.imdecode(np.frombuffer(qr.content, np.uint8), cv2.IMREAD_COLOR)
    url = cv2.QRCodeDetector().detectAndDecode(img)[0]
    parts = urlsplit(url)
    assert parts.path == '/selfit/photo'
    assert parts.query == ('intent=xhs' if stamp else '')
    assert parts.fragment == f'{photo_id}.{SECRET}'
    assert 'share_code' not in url
    assert client.get(f'/api/v1/selfit/mirror/photos/{photo_id}/qr?intent=xhs').status_code == 404
    with photos._database() as db:
        db.execute('UPDATE photos SET expires=?', (time.time() - 1,))
    assert retrieve(client, photo_id, 'qr?intent=xhs').status_code == 410

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.request_logging import RequestTimingMiddleware


def records(caplog):
    return [json.loads(r.message) for r in caplog.records if r.message.startswith('{"event":"http_request"')]


def test_request_id_timing_and_sensitive_values_are_not_logged(caplog):
    app = FastAPI()
    app.add_middleware(RequestTimingMiddleware)
    @app.get('/reports/{token}')
    async def report(token):
        return {'ok': True}
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        response = TestClient(app).get('/reports/SECRET_TOKEN?phone=13800000000', headers={'Authorization':'Bearer SECRET_AUTH', 'X-Request-ID':'UNTRUSTED_ID'})
    row, = records(caplog)
    assert row['status'] == 200
    assert row['route'] == '/reports/{token}'
    assert row['request_id'] == response.headers['x-request-id']
    assert row['duration_ms'] >= row['headers_ms'] >= 0
    assert row['handler_ms'] >= row['duration_ms']
    assert row['response_bytes'] == len(response.content)
    assert row['timestamp'].endswith('+00:00')
    assert row['outcome'] == 'completed'
    for secret in ('SECRET_TOKEN', '13800000000', 'SECRET_AUTH', 'UNTRUSTED_ID'):
        assert secret not in json.dumps(row)


def test_errors_and_unmatched_routes_are_recorded(caplog):
    app = FastAPI()
    app.add_middleware(RequestTimingMiddleware)
    @app.get('/limited')
    async def limited():
        raise HTTPException(429, 'slow down')
    @app.get('/broken')
    async def broken():
        raise RuntimeError('PRIVATE_ERROR_DETAIL')
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        assert client.get('/limited').status_code == 429
        assert client.get('/broken').status_code == 500
        assert client.get('/secret-unknown-token').status_code == 404
    limited, broken, unknown = records(caplog)
    assert limited['status'] == 429
    assert broken['status'] == 500 and broken['error_type'] == 'RuntimeError'
    assert broken['outcome'] == 'error'
    assert unknown['route'] == '/unmatched'
    assert 'PRIVATE_ERROR_DETAIL' not in json.dumps(broken)


def test_streaming_duration_waits_for_last_body_and_marks_slow(caplog, monkeypatch):
    monkeypatch.setenv('SELFIT_SLOW_REQUEST_MS', '10')
    async def endpoint(scope, receive, send):
        scope['route'] = SimpleNamespace(path='/stream')
        await send({'type':'http.response.start', 'status':200, 'headers':[]})
        await send({'type':'http.response.body', 'body':b'abc', 'more_body':True})
        await asyncio.sleep(.025)
        await send({'type':'http.response.body', 'body':b'def', 'more_body':False})
    async def run():
        async def receive(): return {'type':'http.request','body':b''}
        async def send(message): pass
        await RequestTimingMiddleware(endpoint)({'type':'http','path':'/stream','method':'GET'}, receive, send)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        asyncio.run(run())
    row, = records(caplog)
    assert row['duration_ms'] >= 20
    assert row['duration_ms'] > row['headers_ms']
    assert row['response_bytes'] == 6 and row['slow']


def test_disconnect_is_logged_and_cancellation_propagates(caplog):
    async def endpoint(scope, receive, send):
        await receive()
        raise asyncio.CancelledError()
    async def run():
        async def receive(): return {'type':'http.disconnect'}
        async def send(message): pass
        with pytest.raises(asyncio.CancelledError):
            await RequestTimingMiddleware(endpoint)({'type':'http','path':'/upload','method':'POST'}, receive, send)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        asyncio.run(run())
    row, = records(caplog)
    assert row['status'] == 499 and row['outcome'] == 'disconnected'


def test_guard_short_circuit_is_logged(caplog):
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.middleware('http')
    async def reject(request, call_next):
        return JSONResponse({'error':'too large'}, status_code=413)
    app.add_middleware(RequestTimingMiddleware)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        response = TestClient(app).post('/upload?secret=hidden', content=b'x')
    row, = records(caplog)
    assert row['status'] == 413
    assert row['outcome'] == 'completed'
    assert row['request_id'] == response.headers['x-request-id']


def test_wrapped_disconnect_is_recognized():
    from starlette.requests import ClientDisconnect
    from app.request_logging import _is_disconnect
    assert _is_disconnect(ExceptionGroup('wrapped', [ClientDisconnect()]))
    assert not _is_disconnect(ExceptionGroup('mixed', [ClientDisconnect(), ValueError()]))


def test_native_photo_download_access_log_redacts_capability(caplog):
    RequestTimingMiddleware(None)
    path = '/api/v1/selfit/mirror/photos/mp_123/files/print.png'
    with caplog.at_level(logging.INFO, logger='uvicorn.access'):
        logging.getLogger('uvicorn.access').info('%s - "%s %s HTTP/%s" %d',
            '127.0.0.1', 'GET', path + '?expires=123&signature=PRIVATE_TICKET', '1.1', 200)
    assert path in caplog.text
    assert 'PRIVATE_TICKET' not in caplog.text
    assert '?expires=' not in caplog.text


def test_share_event_access_log_redacts_capability(caplog):
    RequestTimingMiddleware(None)
    with caplog.at_level(logging.INFO, logger='uvicorn.access'):
        logging.getLogger('uvicorn.access').info('%s - "%s %s HTTP/%s" %d',
            '127.0.0.1', 'POST', '/api/v1/selfit/mirror/photos/mp_123/share-events?signature=PRIVATE_EVENT', '1.1', 204)
    assert 'PRIVATE_EVENT' not in caplog.text and 'share-events' in caplog.text


@pytest.mark.parametrize('agent,family,platform', [
    ('iPhone MicroMessenger/8.0 SECRET_UA', 'wechat', 'ios'),
    ('discover/9.0 iPhone SECRET_UA', 'xiaohongshu', 'ios'),
    ('CFNetwork/123 Darwin/24', 'apple_network', 'other'),
    ('Android Chrome/130', 'chrome', 'android'),
])
def test_photo_request_source_is_classified_without_raw_headers(agent, family, platform):
    from app.request_logging import mirror_share_context
    photo = 'mp_' + 'a' * 32
    row = mirror_share_context({'path': f'/api/v1/selfit/mirror/photos/{photo}/files/print.png',
        'headers': [(b'user-agent', agent.encode()), (b'authorization', b'PRIVATE_AUTH'), (b'sec-fetch-dest', b'image')]})
    assert row['client_family'] == family and row['client_platform'] == platform
    assert row['fetch_destination'] == 'image' and len(row['photo_ref']) == 12
    assert all(secret not in json.dumps(row) for secret in [photo, 'PRIVATE_AUTH', 'SECRET_UA'])


def test_browser_identity_and_native_image_link_identity_are_distinguished():
    from app.request_logging import mirror_share_context
    path = '/api/v1/selfit/mirror/photos/mp_' + 'a' * 32 + '/files/print.png'
    client_id = 'mc_' + 'b' * 32
    direct = mirror_share_context({'path': path, 'headers': [(b'x-selfit-client-id', client_id.encode())]})
    linked = mirror_share_context({'path': path, 'query_string': f'signature=PRIVATE_SIGNATURE&client_id={client_id}'.encode()})
    assert direct['client_id'] == linked['client_id'] == client_id
    assert direct['client_id_source'] == 'header' and linked['client_id_source'] == 'photo_link'
    assert 'PRIVATE_SIGNATURE' not in json.dumps(linked)
    assert mirror_share_context({'path': '/unrelated', 'headers': [(b'x-selfit-client-id', client_id.encode())]}) == {}


@pytest.mark.parametrize('scope', [
    {'headers': [(b'x-selfit-client-id', b'PRIVATE_AUTH')]},
    {'headers': [(b'x-selfit-client-id', b'mc_' + b'a' * 32 + b'\n')]},
    {'query_string': b'client_id=PRIVATE_AUTH'},
    {'query_string': b'client_id=mc_' + b'a' * 32 + b'&client_id=mc_' + b'b' * 32},
    {'query_string': b'client_id=mc_' + b'a' * 32 + b'%0a'},
    {'query_string': b'client_id=' + b'a' * 4097},
    {'query_string': b'x=1&' * 17},
    {'query_string': b'client_id=\xff'},
])
def test_malformed_browser_identity_is_ignored_without_logging_payload(scope):
    from app.request_logging import mirror_client_context
    assert mirror_client_context(scope) == {}

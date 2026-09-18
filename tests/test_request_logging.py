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

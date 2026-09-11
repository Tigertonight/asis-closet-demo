from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import threading

import pytest
from PIL import Image
import requests
from google.oauth2.credentials import Credentials

from app import vertex_image as vertex
from app import tryon, closet


@pytest.fixture
def adc(monkeypatch):
    monkeypatch.setenv("TRYON_GOOGLE_BACKEND", "vertex_adc")
    monkeypatch.setenv("TRYON_VERTEX_PROJECT", "test-project")
    monkeypatch.setenv("TRYON_VERTEX_LOCATION", "global")
    monkeypatch.delenv("TRYON_IMAGE_MODEL", raising=False)
    credentials = Credentials(None, refresh_token="test-refresh-secret", token_uri="https://oauth2.googleapis.com/token",
                              client_id="test-client", client_secret="test-client-secret", quota_project_id="test-project")
    monkeypatch.setattr(vertex, "_credentials", lambda: credentials)
    return credentials


def test_adc_takes_priority_and_is_used_for_cutouts(adc, monkeypatch):
    def forbidden():
        pytest.fail("ADC selection must not discover an old provider key")
    monkeypatch.setattr(tryon, "_has_runway_google_provider", forbidden)
    monkeypatch.setattr(closet, "_has_runway_google_provider", forbidden)
    assert isinstance(tryon._default_provider(), tryon.VertexADCTryOnProvider)
    assert tryon.image_edit_model() == "gemini-3.1-flash-image"
    cutout = closet.AIGarmentCutoutProvider()
    assert cutout._provider_kind() == vertex.MODE
    assert cutout.model == "gemini-3.1-flash-image"
    assert cutout.status() == "available_via_vertex_adc"


def test_adc_missing_credentials_never_falls_back(adc, monkeypatch, tmp_path):
    monkeypatch.setattr(vertex, "_credentials", lambda: (_ for _ in ()).throw(FileNotFoundError("secret")))
    monkeypatch.setattr(tryon, "_has_runway_google_provider", lambda: True)
    provider = tryon._default_provider()
    result = provider.edit(tmp_path/'person', tmp_path/'garment', tmp_path/'mask', 'test', tmp_path)
    assert result["image_path"] is None
    assert result["stage"]["evidence"]["provider"] == vertex.MODE
    assert closet.AIGarmentCutoutProvider().available() is False
    assert "secret" not in json.dumps(result)


def test_adc_real_authorized_session_refreshes_expired_token(adc, monkeypatch):
    refreshes, calls = [], []
    def request(self, method, url, **kwargs):
        assert self.trust_env is False
        response = requests.Response()
        response.status_code = 200
        if url == "https://oauth2.googleapis.com/token":
            refreshes.append(url)
            response._content = json.dumps({"access_token": f"fresh-{len(refreshes)}", "expires_in": 3600, "token_type": "Bearer"}).encode()
        else:
            calls.append(kwargs)
            assert url == vertex.endpoint()
            assert kwargs["headers"]["authorization"] == f"Bearer fresh-{len(refreshes)}"
            assert kwargs["headers"]["x-goog-user-project"] == "test-project"
            assert not any("api-key" in key for key in kwargs["headers"])
            assert kwargs["allow_redirects"] is False
            assert kwargs["timeout"] == (20, 90)
            response._content = b'{"candidates":[]}'
        return response
    monkeypatch.setattr(requests.Session, "request", request)
    for _ in range(2):
        adc.expiry = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        assert vertex.generate_content({"contents": []}, timeout=90) == {"candidates": []}
    assert len(refreshes) == len(calls) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_errors_are_sanitized_and_not_retried(adc, monkeypatch, status):
    from google.auth.transport.requests import AuthorizedSession
    calls = []
    def post(self, *args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = status
        response._content = b'sensitive-response-body'
        return response
    monkeypatch.setattr(AuthorizedSession, "post", post)
    with pytest.raises(RuntimeError, match=f"^Vertex generateContent HTTP {status}$"):
        vertex.generate_content({})
    assert len(calls) == 1


def test_oauth_exception_never_exposes_credentials(adc, monkeypatch):
    from google.auth.transport.requests import AuthorizedSession
    def post(*args, **kwargs):
        raise ValueError("test-refresh-secret test-client-secret")
    monkeypatch.setattr(AuthorizedSession, "post", post)
    with pytest.raises(RuntimeError, match=r"^Vertex ADC request failed \(ValueError\)$"):
        vertex.generate_content({})


def test_resource_ids_cannot_redirect_bearer_token(adc, monkeypatch):
    monkeypatch.setenv("TRYON_VERTEX_LOCATION", "evil.example/path")
    with pytest.raises(ValueError):
        vertex.endpoint()
    assert vertex.configured() is False


def test_tryon_image_response_and_canvas_are_preserved(adc, monkeypatch, tmp_path):
    path = tmp_path / 'person.png'
    Image.new('RGB', (768, 1024), 'white').save(path)
    encoded = base64.b64encode(path.read_bytes()).decode()
    captured = []
    def generate(payload, **kwargs):
        captured.append(payload)
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": encoded}}]}}]}
    monkeypatch.setattr(vertex, "generate_content", generate)
    result = tryon._default_provider().edit(path, path, path, 'Replace the top.', tmp_path)
    assert result["stage"]["status"] == "pass"
    assert result["stage"]["evidence"]["model"] == vertex.DEFAULT_MODEL
    assert Image.open(result["image_path"]).size == (768, 1024)
    assert captured[0]["generationConfig"]["imageConfig"] == {"aspectRatio": "3:4", "imageSize": "2K"}
    assert len(captured[0]["contents"][0]["parts"]) == 4


def test_inventory_and_cutout_use_adc(adc, monkeypatch, tmp_path):
    captured = []
    image = Image.new('RGBA', (256, 256), 'red')
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    def generate(payload, **kwargs):
        captured.append(payload)
        if 'imageConfig' not in payload['generationConfig']:
            return {"candidates": [{"content": {"parts": [{"text": '{"items": []}'}]}}]}
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(buffer.getvalue()).decode()}}]}}]}
    monkeypatch.setattr(vertex, 'generate_content', generate)
    provider = closet.AIGarmentCutoutProvider()
    assert provider._analyze_inventory_with_runway(image, 'List items') == '{"items": []}'
    image.save(tmp_path/'source.png')
    assert provider._generate_cutout(tmp_path/'source.png', 'top').size == (256, 256)
    assert len(captured) == 2


def test_adc_readiness_does_not_accept_legacy_keys(adc, monkeypatch, tmp_path):
    from scripts import check_runtime_readiness as runtime
    env = tmp_path / '.env'
    env.write_text('TRYON_RUNWAY_GOOGLE_URL=https://legacy.example\nTRYON_RUNWAY_GOOGLE_API_KEY=test-key\n')
    monkeypatch.setattr(runtime, '_http_probe', lambda *a, **k: {"reachable": False})
    assert runtime.readiness(env)['ready']['real_tryon'] is True
    monkeypatch.setattr(vertex, 'configured', lambda: False)
    assert runtime.readiness(env)['ready']['real_tryon'] is False


def test_credential_discovery_is_cached_per_thread_and_rotates(monkeypatch, tmp_path):
    import google.auth
    monkeypatch.setenv('TRYON_VERTEX_PROJECT', 'test-project')
    path = tmp_path/'adc.json'
    path.write_text('{}')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', str(path))
    monkeypatch.setattr(vertex, '_state', threading.local())
    seen = []
    def load(*args, **kwargs):
        value = object()
        seen.append(value)
        assert kwargs['quota_project_id'] == 'test-project'
        return value, None
    monkeypatch.setattr(google.auth, 'load_credentials_from_file', load)
    first = vertex._credentials()
    assert vertex._credentials() is first
    thread = threading.Thread(target=vertex._credentials)
    thread.start()
    thread.join()
    assert len(seen) == 2
    path.write_text('{"rotated":true}')
    assert vertex._credentials() is not first
    assert len(seen) == 3


def test_semantic_review_uses_adc_and_ignores_thought_parts(adc, monkeypatch, tmp_path):
    path = tmp_path/'result.png'
    Image.new('RGB', (256, 256), 'white').save(path)
    review = {'items': [{'review_id': 'top-1', 'slot': 'top', 'status': 'matched', 'confidence': 0.9}], 'overall_confidence': 0.9}
    def generate(payload, **kwargs):
        assert 'responseModalities' not in payload['generationConfig']
        return {'candidates': [{'content': {'parts': [{'text': 'not JSON', 'thought': True}, {'text': json.dumps(review)}]}}]}
    monkeypatch.setattr(vertex, 'generate_content', generate)
    result = tryon._review_outfit_semantics(path, {'items': [{'item_id': 'top-1', 'slot': 'top', 'category': 'top'}]})
    assert result['status'] == 'pass'
    assert result['evidence']['provider'] == 'vertex_adc_vision'


def test_completed_cache_is_bound_to_backend_and_model(adc, monkeypatch, tmp_path):
    monkeypatch.setattr(tryon, '_tryon_output_dir', lambda: tmp_path)
    image = tmp_path/'image.png'
    Image.new('RGB', (64, 64)).save(image)
    cache = tmp_path/'cache.json'
    data = {'result': {'image_path': str(image)}}
    tryon._write_completed_tryon_cache(cache, data)
    assert tryon._load_completed_tryon_cache(cache)
    monkeypatch.setenv('TRYON_IMAGE_MODEL', 'another-model')
    assert tryon._load_completed_tryon_cache(cache) is None
    monkeypatch.delenv('TRYON_GOOGLE_BACKEND')
    assert tryon._load_completed_tryon_cache(cache) is None
    tryon._write_completed_tryon_cache(cache, data)
    assert tryon._load_completed_tryon_cache(cache)
    monkeypatch.setenv('TRYON_GOOGLE_BACKEND', 'vertex_adc')
    assert tryon._load_completed_tryon_cache(cache) is None

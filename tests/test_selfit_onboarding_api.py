from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.selfit_onboarding as selfit_onboarding
from app.main import app

API = "/api/v1/selfit"


def _use_tmp_store(monkeypatch, tmp_path: Path) -> None:
    store_dir = tmp_path / "outputs" / "selfit_onboarding"
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_DIR", store_dir)
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_STORE_PATH", store_dir / "sessions.json")


def _create_session(client: TestClient, **kwargs) -> dict:
    response = client.post(f"{API}/sessions", json={"schemaVersion": "selfit-onboarding-v1", "locale": "zh-CN"}, **kwargs)
    assert response.status_code == 201
    return response.json()


def test_create_and_get_session(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    created = _create_session(client)
    session = created["session"]
    assert created["requestId"].startswith("req_")
    assert session["status"] == "draft"
    assert session["revision"] == 1
    assert session["sessionId"].startswith("ses_")
    assert session["expiresAt"].endswith("Z")

    fetched = client.get(f"{API}/sessions/{session['sessionId']}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["sessionId"] == session["sessionId"]


def test_create_session_idempotent_replay(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    headers = {"X-Idempotency-Key": "session_key_1"}
    first = _create_session(client, headers=headers)
    second = _create_session(client, headers=headers)
    assert second["session"]["sessionId"] == first["session"]["sessionId"]

    other = _create_session(client, headers={"X-Idempotency-Key": "session_key_2"})
    assert other["session"]["sessionId"] != first["session"]["sessionId"]


def test_patch_flow_bumps_revision_monotonically(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    profile = client.patch(
        f"{API}/sessions/{session_id}/profile",
        json={"manual": {"skin": "自然白", "faceShape": "椭圆脸", "bodyShape": "梨型"}},
    )
    assert profile.status_code == 200
    assert profile.json()["session"]["revision"] == 2

    preferences = client.patch(
        f"{API}/sessions/{session_id}/preferences",
        json={"axes": {"shape": 42, "energy": 64, "trend": 42}, "palette": "mono"},
    )
    assert preferences.status_code == 200
    assert preferences.json()["session"]["revision"] == 3

    vibe = client.patch(
        f"{API}/sessions/{session_id}/vibe",
        json={"answers": {"occasion": "A", "wardrobe": "B", "expression": "A"}},
    )
    assert vibe.status_code == 200
    assert vibe.json()["session"]["revision"] == 4

    fetched = client.get(f"{API}/sessions/{session_id}").json()["session"]
    assert fetched["revision"] == 4
    assert fetched["completedSteps"] == ["profile", "preferences", "vibe"]


def test_patch_rejects_invalid_enum_with_unified_error(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    response = client.patch(
        f"{API}/sessions/{session_id}/profile",
        json={"manual": {"skin": "不存在肤色"}},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["requestId"].startswith("req_")
    assert payload["error"]["code"] == "validation.invalid_enum"
    assert payload["error"]["retryable"] is False

    palette = client.patch(
        f"{API}/sessions/{session_id}/preferences",
        json={"palette": "neon"},
    )
    assert palette.status_code == 422
    assert palette.json()["error"]["code"] == "validation.invalid_enum"

    vibe = client.patch(
        f"{API}/sessions/{session_id}/vibe",
        json={"answers": {"occasion": "Z"}},
    )
    assert vibe.status_code == 422
    assert vibe.json()["error"]["code"] == "validation.invalid_enum"

    session = client.get(f"{API}/sessions/{session_id}").json()["session"]
    assert session["revision"] == 1


def test_patch_rejects_out_of_range_axes(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    for bad_value in (-1, 101, "high", True):
        response = client.patch(
            f"{API}/sessions/{session_id}/preferences",
            json={"axes": {"shape": bad_value}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation.invalid_value"


def test_unknown_session_returns_expired(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get(f"{API}/sessions/ses_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session.expired"

    patch = client.patch(
        f"{API}/sessions/ses_missing/vibe",
        json={"answers": {"occasion": "A"}},
    )
    assert patch.status_code == 404
    assert patch.json()["error"]["code"] == "session.expired"


def test_expired_session_returns_session_expired(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_ONBOARDING_SESSION_TTL_HOURS", "-1")
    client = TestClient(app)

    session_id = _create_session(client)["session"]["sessionId"]
    response = client.get(f"{API}/sessions/{session_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session.expired"


def test_if_match_conflict_returns_409(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    ok = client.patch(
        f"{API}/sessions/{session_id}/vibe",
        json={"answers": {"occasion": "A"}},
        headers={"If-Match": "1"},
    )
    assert ok.status_code == 200
    assert ok.json()["session"]["revision"] == 2

    conflict = client.patch(
        f"{API}/sessions/{session_id}/vibe",
        json={"answers": {"occasion": "B"}},
        headers={"If-Match": "1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "session.revision_conflict"
    assert client.get(f"{API}/sessions/{session_id}").json()["session"]["revision"] == 2


def test_idempotent_patch_replay_does_not_bump_revision(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    headers = {"X-Idempotency-Key": "patch_vibe_1"}
    body = {"answers": {"occasion": "A"}}
    first = client.patch(f"{API}/sessions/{session_id}/vibe", json=body, headers=headers)
    second = client.patch(f"{API}/sessions/{session_id}/vibe", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["session"]["revision"] == first.json()["session"]["revision"] == 2

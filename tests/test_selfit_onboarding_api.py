from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.selfit_onboarding as selfit_onboarding
import app.selfit_photo as selfit_photo
from app.main import app

API = "/api/v1/selfit"
FIXTURE_IMAGES = Path(__file__).resolve().parent / "fixtures" / "images"


def _use_tmp_store(monkeypatch, tmp_path: Path) -> None:
    store_dir = tmp_path / "outputs" / "selfit_onboarding"
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_DIR", store_dir)
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_STORE_PATH", store_dir / "sessions.json")
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_ASSET_DIR", store_dir / "assets")


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


def _upload_photo(client: TestClient, session_id: str, kind: str, content: bytes, filename: str = "photo.jpg", **kwargs):
    return client.post(
        f"{API}/sessions/{session_id}/photos/{kind}",
        files={"image": (filename, content)},
        **kwargs,
    )


def _jpeg_bytes(color: tuple[int, int, int] = (200, 180, 170)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, "JPEG")
    return buffer.getvalue()


def test_photo_upload_accepted_and_saves_asset(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    # 契约测试只关心接受后的存储行为，照片检测 stub 为全放行。
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    response = _upload_photo(client, session_id, "face", _jpeg_bytes())
    assert response.status_code == 200
    payload = response.json()
    photo = payload["photo"]
    assert payload["requestId"].startswith("req_")
    assert payload["revision"] == 2
    assert photo["kind"] == "face"
    assert photo["status"] == "accepted"
    assert photo["code"] == "photo.accepted"
    assert photo["message"] == "面部照可用"
    assert photo["issues"] == []
    assert photo["assetId"].startswith("asset_face_")

    assets = list((tmp_path / "outputs" / "selfit_onboarding" / "assets" / session_id).glob("asset_face_*"))
    assert len(assets) == 1

    body = _upload_photo(client, session_id, "body", _jpeg_bytes())
    assert body.status_code == 200
    assert body.json()["photo"]["status"] == "accepted"
    session = client.get(f"{API}/sessions/{session_id}").json()["session"]
    assert session["revision"] == 3
    assert session["completedSteps"] == ["photos"]


def test_photo_business_rejection_returns_200_without_asset(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        selfit_photo,
        "_inspector",
        lambda image, kind: selfit_photo.PhotoInspection(accepted=False, issues=["insufficient_light", "blurred"]),
    )
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    response = _upload_photo(client, session_id, "face", _jpeg_bytes())
    assert response.status_code == 200
    photo = response.json()["photo"]
    assert photo["status"] == "rejected"
    assert photo["assetId"] is None
    assert photo["code"] == "photo.insufficient_light"
    assert photo["issues"] == ["insufficient_light", "blurred"]
    assert "光线不充足" in photo["message"]
    assert not (tmp_path / "outputs" / "selfit_onboarding" / "assets" / session_id).exists()


def test_photo_unknown_issues_fall_back_to_unsupported(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        selfit_photo,
        "_inspector",
        lambda image, kind: selfit_photo.PhotoInspection(accepted=False, issues=["algorithm_typo"]),
    )
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    photo = _upload_photo(client, session_id, "body", _jpeg_bytes()).json()["photo"]
    assert photo["status"] == "rejected"
    assert photo["code"] == "photo.unsupported_content"
    assert photo["issues"] == ["unsupported_content"]


def test_photo_protocol_errors(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    missing = client.post(f"{API}/sessions/{session_id}/photos/face")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "photo.image_missing"

    too_large = _upload_photo(client, session_id, "face", b"0" * (12 * 1024 * 1024 + 1))
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "photo.too_large"

    undecodable = _upload_photo(client, session_id, "face", b"not an image")
    assert undecodable.status_code == 400
    assert undecodable.json()["error"]["code"] == "photo.invalid_image"

    gif_buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(gif_buffer, "GIF")
    unsupported = _upload_photo(client, session_id, "face", gif_buffer.getvalue(), filename="photo.gif")
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "photo.unsupported_type"

    invalid_kind = _upload_photo(client, session_id, "pet", _jpeg_bytes())
    assert invalid_kind.status_code == 422
    assert invalid_kind.json()["error"]["code"] == "validation.invalid_enum"


def test_photo_upload_requires_active_session(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    response = _upload_photo(client, "ses_missing", "face", _jpeg_bytes())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session.expired"


def test_photo_upload_idempotent_replay(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    # 契约测试只关心幂等回放，照片检测 stub 为全放行。
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    headers = {"X-Idempotency-Key": "photo_face_1"}
    first = _upload_photo(client, session_id, "face", _jpeg_bytes(), headers=headers)
    second = _upload_photo(client, session_id, "face", _jpeg_bytes(), headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["photo"]["assetId"] == first.json()["photo"]["assetId"]
    assert second.json()["revision"] == first.json()["revision"] == 2
    assets = list((tmp_path / "outputs" / "selfit_onboarding" / "assets" / session_id).glob("asset_face_*"))
    assert len(assets) == 1

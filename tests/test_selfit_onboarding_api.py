from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth
import app.selfit_onboarding as selfit_onboarding
import app.selfit_photo as selfit_photo
import app.selfit_report as selfit_report
import app.storage as storage
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


def _create_report_job(client: TestClient, session_id: str, **kwargs) -> dict:
    response = client.post(f"{API}/sessions/{session_id}/report-jobs", json={}, **kwargs)
    assert response.status_code == 202
    return response.json()


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"{API}/report-jobs/{job_id}").json()["job"]
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"report job {job_id} did not finish in {timeout}s")


def test_report_job_lifecycle_completes_with_report(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        selfit_report,
        "_builder",
        lambda session: {"title": "中性利落派", "traits": ["冷调柔和"]},
    )
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    created = _create_report_job(client, session_id)
    job = created["job"]
    assert created["requestId"].startswith("req_")
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["pollAfterMs"] == 800

    finished = _wait_for_job(client, job["jobId"])
    assert finished["status"] == "completed"
    assert finished["progress"] == 100
    assert finished["stage"] == "finalizing"
    assert finished["reportId"].startswith("rep_")
    assert finished["report"]["title"] == "中性利落派"

    fetched = client.get(f"{API}/reports/{finished['reportId']}")
    assert fetched.status_code == 200
    assert fetched.json()["report"]["traits"] == ["冷调柔和"]


def test_report_job_processing_state(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocking_builder(session: dict) -> dict:
        started.set()
        assert release.wait(timeout=10)
        return {"title": "中性利落派"}

    monkeypatch.setattr(selfit_report, "_builder", blocking_builder)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    job = _create_report_job(client, session_id)["job"]
    assert started.wait(timeout=5)
    polled = client.get(f"{API}/report-jobs/{job['jobId']}").json()["job"]
    assert polled["status"] == "processing"
    assert polled["stage"] in {"profile", "inspiration", "composition", "finalizing"}
    assert 0 < polled["progress"] < 100
    assert polled["pollAfterMs"] == 800
    assert "reportId" not in polled

    release.set()
    finished = _wait_for_job(client, job["jobId"])
    assert finished["status"] == "completed"
    assert finished["report"]["title"] == "中性利落派"


def test_report_job_idempotent_creation(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    headers = {"X-Idempotency-Key": "report_1"}
    first = _create_report_job(client, session_id, headers=headers)
    second = _create_report_job(client, session_id, headers=headers)
    assert second["job"]["jobId"] == first["job"]["jobId"]


def test_report_job_not_found(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get(f"{API}/report-jobs/job_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "report.job_not_found"

    report = client.get(f"{API}/reports/rep_missing")
    assert report.status_code == 404
    assert report.json()["error"]["code"] == "report.not_found"


def test_report_job_requires_active_session(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(f"{API}/sessions/ses_missing/report-jobs", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session.expired"


def test_report_job_builder_failure_marks_failed(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)

    def broken_builder(session: dict) -> dict:
        raise RuntimeError("style engine down")

    monkeypatch.setattr(selfit_report, "_builder", broken_builder)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    job = _create_report_job(client, session_id)["job"]
    finished = _wait_for_job(client, job["jobId"])
    assert finished["status"] == "failed"
    assert finished["error"]["code"] == "report.generation_failed"
    assert finished["error"]["retryable"] is True


def test_report_builder_receives_session_profile(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    captured: list[dict] = []

    def spy_builder(session: dict) -> dict:
        captured.append(session)
        return {}

    monkeypatch.setattr(selfit_report, "_builder", spy_builder)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]
    client.patch(f"{API}/sessions/{session_id}/profile", json={"manual": {"skin": "自然白", "bodyShape": "梨型"}})
    client.patch(f"{API}/sessions/{session_id}/vibe", json={"answers": {"occasion": "A"}})

    job = _create_report_job(client, session_id)["job"]
    assert _wait_for_job(client, job["jobId"])["status"] == "completed"
    assert len(captured) == 1
    assert captured[0]["manual"] == {"skin": "自然白", "bodyShape": "梨型"}
    assert captured[0]["vibe"] == {"occasion": "A"}


def _create_report(client: TestClient, monkeypatch, report_data: dict | None = None) -> str:
    monkeypatch.setattr(
        selfit_report,
        "_builder",
        lambda session: report_data if report_data is not None else {},
    )
    session_id = _create_session(client)["session"]["sessionId"]
    job = _create_report_job(client, session_id)["job"]
    finished = _wait_for_job(client, job["jobId"])
    assert finished["status"] == "completed"
    return finished["reportId"]


def test_outfit_request_created_and_idempotent(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    report_id = _create_report(client, monkeypatch)

    response = client.post(
        f"{API}/reports/{report_id}/outfit-requests",
        json={"source": "report", "intent": "complete_look"},
    )
    assert response.status_code == 202
    outfit = response.json()["request"]
    assert outfit["requestId"].startswith("outfit_")
    assert outfit["status"] == "queued"

    headers = {"X-Idempotency-Key": "outfit_1"}
    first = client.post(f"{API}/reports/{report_id}/outfit-requests", json={}, headers=headers)
    second = client.post(f"{API}/reports/{report_id}/outfit-requests", json={}, headers=headers)
    assert second.json()["request"]["requestId"] == first.json()["request"]["requestId"]

    missing = client.post(f"{API}/reports/rep_missing/outfit-requests", json={})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "report.not_found"


def test_share_asset_ready_and_downloadable(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    report_id = _create_report(
        client,
        monkeypatch,
        report_data={
            "eyebrow": "SOFT COOL",
            "title": "中性利落派",
            "traits": ["冷调柔和", "高质感"],
            "colors": [{"name": "橄榄绿", "value": "#c8c487"}],
        },
    )

    response = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 1, "channel": "保存单张", "format": "png"},
    )
    assert response.status_code == 200
    asset = response.json()["asset"]
    assert asset["assetId"].startswith("share_")
    assert asset["status"] == "ready"
    assert asset["slideIndex"] == 1
    assert asset["channel"] == "保存单张"
    assert asset["expiresAt"].endswith("Z")

    download = client.get(asset["downloadUrl"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert len(download.content) > 1000

    for slide_index in (0, 2):
        slid = client.post(
            f"{API}/reports/{report_id}/share-assets",
            json={"slideIndex": slide_index, "channel": "发笔记", "format": "png"},
        )
        assert slid.status_code == 200
        assert slid.json()["asset"]["slideIndex"] == slide_index


def test_share_asset_idempotent(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    report_id = _create_report(client, monkeypatch)

    headers = {"X-Idempotency-Key": "share_1"}
    body = {"slideIndex": 0, "channel": "微信好友", "format": "png"}
    first = client.post(f"{API}/reports/{report_id}/share-assets", json=body, headers=headers)
    second = client.post(f"{API}/reports/{report_id}/share-assets", json=body, headers=headers)
    assert second.json()["asset"]["assetId"] == first.json()["asset"]["assetId"]
    shared_dir = tmp_path / "outputs" / "selfit_onboarding" / "assets" / "shared"
    assert len(list(shared_dir.glob("share_*"))) == 1


def test_share_asset_validation_errors(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    report_id = _create_report(client, monkeypatch)

    bad_slide = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 5, "channel": "保存单张"},
    )
    assert bad_slide.status_code == 422
    assert bad_slide.json()["error"]["code"] == "validation.invalid_value"

    bad_channel = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 0, "channel": "发微博"},
    )
    assert bad_channel.status_code == 422
    assert bad_channel.json()["error"]["code"] == "validation.invalid_enum"

    bad_format = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 0, "channel": "保存单张", "format": "webp"},
    )
    assert bad_format.status_code == 422
    assert bad_format.json()["error"]["code"] == "validation.invalid_enum"

    missing = client.post(
        f"{API}/reports/rep_missing/share-assets",
        json={"slideIndex": 0, "channel": "保存单张"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "report.not_found"

    download = client.get(f"{API}/share-assets/share_missing/download")
    assert download.status_code == 404
    assert download.json()["error"]["code"] == "share.asset_not_found"


def test_share_asset_renderer_failure(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    report_id = _create_report(client, monkeypatch)

    def broken_renderer(report, slide_index, channel, image_format):
        raise RuntimeError("render down")

    import app.selfit_share as selfit_share

    monkeypatch.setattr(selfit_share, "_renderer", broken_renderer)
    response = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 0, "channel": "保存单张"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "share.render_failed"
    assert response.json()["error"]["retryable"] is True


def test_selfit_api_rate_limit_uses_contract_shape(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("SELFIT_API_RATE_LIMIT", "2")
    client = TestClient(app)

    first = client.post(f"{API}/sessions", json={})
    second = client.post(f"{API}/sessions", json={})
    third = client.post(f"{API}/sessions", json={})
    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
    payload = third.json()
    assert payload["error"]["code"] == "rate_limited"
    assert payload["error"]["retryable"] is True
    assert payload["error"]["details"]["retryAfterSeconds"] >= 1
    assert payload["requestId"].startswith("req_")
    assert third.headers["Retry-After"]


def test_rate_limit_counts_authenticated_users_separately(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("SELFIT_API_RATE_LIMIT", "2")
    client = TestClient(app)

    def login(phone: str) -> dict[str, str]:
        start = client.post("/auth/phone/start", json={"phone": phone}).json()
        verified = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()
        return {"Authorization": f"Bearer {verified['access_token']}"}

    user_a = login("13800000001")
    user_b = login("13800000002")

    for headers in (user_a, user_b):
        assert client.post(f"{API}/sessions", json={}, headers=headers).status_code == 201
        assert client.post(f"{API}/sessions", json={}, headers=headers).status_code == 201
        limited = client.post(f"{API}/sessions", json={}, headers=headers)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"


def test_selfit_page_injects_server_config(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setenv("SELFIT_ONBOARDING_API_MODE", "live")
    page = client.get("/selfit")
    assert page.status_code == 200
    assert "window.__SELFIT_CONFIG__" in page.text
    assert '"apiMode": "live"' in page.text
    assert page.text.index("window.__SELFIT_CONFIG__") < page.text.index("selfit-api.js")

    monkeypatch.setenv("SELFIT_ONBOARDING_API_MODE", "mock")
    page = client.get("/selfit/demo")
    assert '"apiMode": "mock"' in page.text


def test_delete_session_cascades_records_and_assets(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)
    client = TestClient(app)
    session_id = _create_session(client)["session"]["sessionId"]

    photo = client.post(
        f"{API}/sessions/{session_id}/photos/face", files={"image": ("a.jpg", _jpeg_bytes())}
    ).json()["photo"]
    assert photo["status"] == "accepted"
    monkeypatch.setattr(selfit_report, "_builder", lambda session: {"title": "中性利落派"})
    job = _create_report_job(client, session_id)["job"]
    report_id = _wait_for_job(client, job["jobId"])["reportId"]
    share = client.post(
        f"{API}/reports/{report_id}/share-assets",
        json={"slideIndex": 0, "channel": "保存单张", "format": "png"},
    ).json()["asset"]

    asset_dir = tmp_path / "outputs" / "selfit_onboarding" / "assets"
    assert list(asset_dir.glob(f"{session_id}/asset_face_*"))
    assert list(asset_dir.glob("shared/share_*"))

    deleted = client.delete(f"{API}/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["session"]["status"] == "deleted"

    assert client.get(f"{API}/sessions/{session_id}").status_code == 404
    assert client.get(f"{API}/reports/{report_id}").status_code == 404
    assert client.get(share["downloadUrl"]).status_code == 404
    assert not list(asset_dir.glob(f"{session_id}/asset_face_*"))
    assert not list(asset_dir.glob("shared/share_*"))

    again = client.delete(f"{API}/sessions/{session_id}")
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "session.expired"

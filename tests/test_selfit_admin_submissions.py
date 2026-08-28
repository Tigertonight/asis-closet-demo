"""管理后台「用户报告与照片」接口的测试。

覆盖：
- 鉴权：匿名 / 手机号用户不可访问，管理员可以；
- 提交列表与详情：App 上传与智能镜两种来源、报告摘要与完整数据、手机号关联；
- 照片下载：智能镜原始/美颜两个版本、App 上传照片、下载响应头；
- 镜子拍摄记录：未领取的拍摄也能列出并下载（现场打印兜底）。
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth
import app.selfit_admin_submissions as admin_submissions
import app.selfit_mirror_handoff as mirror_handoff
import app.selfit_onboarding as onboarding
import app.selfit_photo as selfit_photo
import app.selfit_report as selfit_report
from app.main import app

API = "/api/v1/selfit"


def _jpeg_bytes(color: str = "#c7a18f") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (120, 160), color).save(output, "JPEG")
    return output.getvalue()


def _use_tmp_stores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "admin-submissions-test-secret")
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")
    monkeypatch.setattr(mirror_handoff, "MIRROR_DIR", tmp_path / "outputs" / "selfit_mirror")
    monkeypatch.setattr(mirror_handoff, "HANDOFF_STORE_PATH", mirror_handoff.MIRROR_DIR / "handoffs.json")
    monkeypatch.setattr(mirror_handoff, "MIRROR_ASSET_DIR", mirror_handoff.MIRROR_DIR / "assets")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_DIR", tmp_path / "outputs" / "selfit_onboarding")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_STORE_PATH", onboarding.SELFIT_ONBOARDING_DIR / "sessions.json")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_ASSET_DIR", onboarding.SELFIT_ONBOARDING_DIR / "assets")
    monkeypatch.setattr(
        admin_submissions, "HIDDEN_STORE_PATH", tmp_path / "outputs" / "admin_hidden.json"
    )
    # 照片检测走全放行，避免测试跑真实 CV 模型
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)


def _admin_login(client: TestClient, monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "admin-test-pw")
    response = client.post("/admin/api/login", json={"password": "admin-test-pw"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _login_phone(client: TestClient, phone: str) -> dict[str, str]:
    response = client.post("/auth/phone/direct", json={"phone": phone})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_mirror_handoff(client: TestClient, *, retouched: bytes | None = None) -> dict:
    files = {"photo": ("capture.jpg", _jpeg_bytes("#c7a18f"), "image/jpeg")}
    if retouched is not None:
        files["retouched"] = ("capture-retouched.jpg", retouched, "image/jpeg")
    response = client.post(
        "/api/v1/selfit/mirror/analyze",
        files=files,
        data={"result": json.dumps({"suit_completed": True, "summary": "ok"})},
    )
    assert response.status_code == 201
    return response.json()


def _claim_handoff(client: TestClient, payload: dict, headers: dict[str, str]) -> dict:
    token = payload["qrImageUrl"].split("/handoffs/", 1)[1].rsplit("/qr", 1)[0]
    response = client.post(f"/api/v1/selfit/mirror/handoffs/{token}/claim", headers=headers)
    assert response.status_code == 200
    return response.json()


def _wait_for_report(client: TestClient, job_id: str, headers: dict[str, str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"{API}/report-jobs/{job_id}", headers=headers).json()["job"]
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"report job {job_id} did not finish in {timeout}s")


def test_submissions_require_admin(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    anonymous = client.get("/admin/api/submissions")
    phone_headers = _login_phone(client, "13800000901")
    as_phone_user = client.get("/admin/api/submissions", headers=phone_headers)
    admin_headers = _admin_login(client, monkeypatch)
    as_admin = client.get("/admin/api/submissions", headers=admin_headers)

    assert anonymous.status_code == 401
    assert as_phone_user.status_code == 403
    assert as_admin.status_code == 200
    assert as_admin.json()["submissions"] == []


def test_mirror_submission_lists_report_and_both_photo_versions(
    monkeypatch, tmp_path: Path
) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setattr(
        selfit_report,
        "_builder",
        lambda session: {
            "typeId": "neon",
            "title": "霓虹先锋",
            "traits": ["大胆", "亮眼"],
            "colors": [{"name": "霓虹粉", "value": "#ff4d6d"}],
            "advice": ["大面积穿适合色"],
        },
    )
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    user_headers = _login_phone(client, "13800000801")
    handoff = _create_mirror_handoff(client, retouched=_jpeg_bytes("#e8b4b8"))
    claimed = _claim_handoff(client, handoff, user_headers)
    session_id = claimed["session"]["sessionId"]

    client.patch(f"{API}/sessions/{session_id}/profile", json={"manual": {"skin": "暖白肤"}}, headers=user_headers)
    client.patch(
        f"{API}/sessions/{session_id}/vibe",
        json={"answers": {"occasion": "A", "wardrobe": "B", "expression": "A"}},
        headers=user_headers,
    )
    job = client.post(f"{API}/sessions/{session_id}/report-jobs", json={}, headers=user_headers).json()["job"]
    finished = _wait_for_report(client, job["jobId"], user_headers)
    assert finished["status"] == "completed"

    submissions = client.get("/admin/api/submissions", headers=admin_headers).json()["submissions"]
    assert len(submissions) == 1
    row = submissions[0]
    assert row["sessionId"] == session_id
    assert row["source"] == "mirror"
    assert row["phone"] == "+8613800000801"
    assert row["report"]["title"] == "霓虹先锋"
    assert row["report"]["typeId"] == "neon"
    assert row["manual"] == {"skin": "暖白肤"}
    assert row["vibe"] == {"occasion": "A", "wardrobe": "B", "expression": "A"}
    mirror = row["mirrorPhotos"]
    assert mirror["original"]["previewUrl"] == f"/admin/api/submissions/{session_id}/mirror-photos/original"
    assert mirror["original"]["downloadUrl"].endswith("?download=1")
    assert mirror["retouched"]["editState"] == "retouched"

    detail = client.get(f"/admin/api/submissions/{session_id}", headers=admin_headers).json()["submission"]
    assert detail["reportData"]["title"] == "霓虹先锋"
    assert detail["reportData"]["colors"][0]["name"] == "霓虹粉"
    assert detail["shareAssets"] == []


def test_mirror_photo_download_returns_original_and_retouched_bytes(
    monkeypatch, tmp_path: Path
) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    original_bytes = _jpeg_bytes("#c7a18f")
    retouched_bytes = _jpeg_bytes("#e8b4b8")
    user_headers = _login_phone(client, "13800000802")
    handoff = _create_mirror_handoff(client, retouched=retouched_bytes)
    claimed = _claim_handoff(client, handoff, user_headers)
    session_id = claimed["session"]["sessionId"]

    retouched = client.get(
        f"/admin/api/submissions/{session_id}/mirror-photos/retouched?download=1",
        headers=admin_headers,
    )
    assert retouched.status_code == 200
    assert retouched.headers["content-type"].startswith("image/jpeg")
    assert "attachment" in retouched.headers.get("content-disposition", "")
    assert "mirror_retouched" in retouched.headers.get("content-disposition", "")
    assert retouched.content == retouched_bytes

    original = client.get(
        f"/admin/api/submissions/{session_id}/mirror-photos/original",
        headers=admin_headers,
    )
    assert original.status_code == 200
    assert original.content == original_bytes

    # 手机照片不经镜子美颜时是同一个文件（passthrough），但两个入口都可下载
    missing = client.get(
        f"/admin/api/submissions/{session_id}/mirror-photos/unknown",
        headers=admin_headers,
    )
    assert missing.status_code == 404


def test_app_submission_lists_uploaded_photos_and_download(
    monkeypatch, tmp_path: Path
) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    face_bytes = _jpeg_bytes("#d8c3aa")
    upload = client.post(
        f"{API}/sessions/{session_id}/photos/face",
        files={"image": ("face.jpg", face_bytes, "image/jpeg")},
    )
    assert upload.status_code == 200
    assert upload.json()["photo"]["status"] == "accepted"

    submissions = client.get("/admin/api/submissions", headers=admin_headers).json()["submissions"]
    row = submissions[0]
    assert row["source"] == "app"
    assert row["report"] is None
    assert row["mirrorPhotos"] is None
    assert [photo["kind"] for photo in row["photos"]] == ["face"]

    download = client.get(
        f"/admin/api/submissions/{session_id}/photos/face?download=1",
        headers=admin_headers,
    )
    assert download.status_code == 200
    assert "attachment" in download.headers.get("content-disposition", "")
    assert download.content == face_bytes


def test_mirror_captures_include_unclaimed_and_allow_download(
    monkeypatch, tmp_path: Path
) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    retouched_bytes = _jpeg_bytes("#e8b4b8")
    user_headers = _login_phone(client, "13800000803")
    claimed_handoff = _create_mirror_handoff(client, retouched=retouched_bytes)
    _claim_handoff(client, claimed_handoff, user_headers)

    unclaimed_bytes = _jpeg_bytes("#b7d4c3")
    unclaimed_handoff = _create_mirror_handoff(client, retouched=unclaimed_bytes)
    unclaimed_id = unclaimed_handoff["handoffId"]

    captures = client.get("/admin/api/mirror-captures", headers=admin_headers).json()["captures"]
    assert len(captures) == 2
    by_id = {row["handoffId"]: row for row in captures}
    assert by_id[claimed_handoff["handoffId"]]["status"] == "claimed"
    assert by_id[claimed_handoff["handoffId"]]["phone"] == "+8613800000803"
    unclaimed = by_id[unclaimed_id]
    assert unclaimed["status"] == "pending"
    assert unclaimed["phone"] is None
    assert unclaimed["original"]["previewUrl"] == f"/admin/api/mirror-captures/{unclaimed_id}/photos/original"

    download = client.get(
        f"/admin/api/mirror-captures/{unclaimed_id}/photos/retouched?download=1",
        headers=admin_headers,
    )
    assert download.status_code == 200
    assert download.content == unclaimed_bytes

    preview = client.get(
        f"/admin/api/mirror-captures/{unclaimed_id}/photos/original",
        headers=admin_headers,
    )
    assert preview.status_code == 200

    missing = client.get(
        "/admin/api/mirror-captures/mho_missing/photos/original",
        headers=admin_headers,
    )
    assert missing.status_code == 404


def test_hide_submission_is_soft_delete_and_recoverable(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    face_bytes = _jpeg_bytes("#d8c3aa")
    upload = client.post(
        f"{API}/sessions/{session_id}/photos/face",
        files={"image": ("face.jpg", face_bytes, "image/jpeg")},
    )
    assert upload.status_code == 200
    asset_file = list(
        (tmp_path / "outputs" / "selfit_onboarding" / "assets" / session_id).glob("asset_face_*")
    )[0]

    hidden = client.post(
        f"/admin/api/submissions/{session_id}/hide", headers=admin_headers
    )
    assert hidden.status_code == 200
    assert hidden.json() == {"status": "ok", "hidden": True}

    payload = client.get("/admin/api/submissions", headers=admin_headers).json()
    assert [row["sessionId"] for row in payload["submissions"]] == []
    assert [item["id"] for item in payload["hidden"]] == [session_id]
    # 软删除：照片资产与会话记录仍在磁盘上，详情接口也可访问
    assert asset_file.is_file()
    assert asset_file.read_bytes() == face_bytes
    detail = client.get(f"/admin/api/submissions/{session_id}", headers=admin_headers)
    assert detail.status_code == 200

    restored = client.post(
        f"/admin/api/submissions/{session_id}/unhide", headers=admin_headers
    )
    assert restored.status_code == 200
    payload = client.get("/admin/api/submissions", headers=admin_headers).json()
    assert [row["sessionId"] for row in payload["submissions"]] == [session_id]
    assert payload["hidden"] == []

    missing = client.post(
        "/admin/api/submissions/ses_missing/hide", headers=admin_headers
    )
    assert missing.status_code == 404


def test_hide_mirror_capture_is_soft_delete_and_recoverable(
    monkeypatch, tmp_path: Path
) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    retouched_bytes = _jpeg_bytes("#e8b4b8")
    handoff = _create_mirror_handoff(client, retouched=retouched_bytes)
    handoff_id = handoff["handoffId"]
    asset_dir = tmp_path / "outputs" / "selfit_mirror" / "assets" / handoff_id
    assert any(asset_dir.glob("asset_retouched_*"))

    hidden = client.post(
        f"/admin/api/mirror-captures/{handoff_id}/hide", headers=admin_headers
    )
    assert hidden.status_code == 200

    payload = client.get("/admin/api/mirror-captures", headers=admin_headers).json()
    assert [row["handoffId"] for row in payload["captures"]] == []
    assert [item["id"] for item in payload["hidden"]] == [handoff_id]
    # 软删除：磁盘上的原始/美颜照片都还在，下载接口仍可用
    assert any(asset_dir.glob("asset_original_*"))
    assert any(asset_dir.glob("asset_retouched_*"))
    download = client.get(
        f"/admin/api/mirror-captures/{handoff_id}/photos/retouched?download=1",
        headers=admin_headers,
    )
    assert download.status_code == 200
    assert download.content == retouched_bytes

    restored = client.post(
        f"/admin/api/mirror-captures/{handoff_id}/unhide", headers=admin_headers
    )
    assert restored.status_code == 200
    payload = client.get("/admin/api/mirror-captures", headers=admin_headers).json()
    assert [row["handoffId"] for row in payload["captures"]] == [handoff_id]


def test_rejected_upload_photo_is_kept_and_listed(monkeypatch, tmp_path: Path) -> None:
    """App 上传被拒的照片：资产照常落盘 + 后台可查、可下载、带拦截原因。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    def rejecting_inspector(image, kind):
        return selfit_photo.PhotoInspection(
            accepted=False, issues=[selfit_photo.ISSUE_FACE_NOT_FOUND, selfit_photo.ISSUE_BLURRED]
        )

    monkeypatch.setattr(selfit_photo, "_inspector", rejecting_inspector)

    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    face_bytes = _jpeg_bytes("#d8c3aa")
    upload = client.post(
        f"{API}/sessions/{session_id}/photos/face",
        files={"image": ("face.jpg", face_bytes, "image/jpeg")},
    )
    assert upload.status_code == 200
    assert upload.json()["photo"]["status"] == "rejected"

    # 被拒照片也落盘保留
    assets = list((tmp_path / "outputs" / "selfit_onboarding" / "assets" / session_id).glob("asset_face_*"))
    assert len(assets) == 1

    payload = client.get("/admin/api/rejected-photos", headers=admin_headers).json()
    assert len(payload["rejected"]) == 1
    row = payload["rejected"][0]
    assert row["sessionId"] == session_id
    assert row["kind"] == "face"
    assert row["source"] == "app"
    assert "检测不到人脸" in row["issueLabels"]
    assert "不够清晰" in row["issueLabels"]
    assert row["primaryIssue"] == "blurred"
    assert row["previewUrl"] == f"/admin/api/rejected-photos/{row['recordId']}"
    assert payload["breakdown"][0]["issue"] == "blurred"
    assert payload["breakdown"][0]["count"] == 1

    download = client.get(
        f"/admin/api/rejected-photos/{row['recordId']}?download=1", headers=admin_headers
    )
    assert download.status_code == 200
    assert "attachment" in download.headers.get("content-disposition", "")
    assert download.content == face_bytes

    # 隐藏对应提交后，被拒记录也一起隐藏
    client.post(f"/admin/api/submissions/{session_id}/hide", headers=admin_headers)
    payload = client.get("/admin/api/rejected-photos", headers=admin_headers).json()
    assert payload["rejected"] == []


def test_rejected_mirror_hydration_is_recorded(monkeypatch, tmp_path: Path) -> None:
    """镜拍 claim 回填失败：留存在 rejected_photos，下载指向镜子原图。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    original_inspector = selfit_photo.inspect_photo

    def rejecting_inspector(image, kind):
        return selfit_photo.PhotoInspection(
            accepted=False, issues=[selfit_photo.ISSUE_BODY_NOT_COMPLETE]
        )

    monkeypatch.setattr(selfit_photo, "_inspector", rejecting_inspector)

    user_headers = _login_phone(client, "13800000805")
    handoff = _create_mirror_handoff(client)
    claimed = _claim_handoff(client, handoff, user_headers)
    session_id = claimed["session"]["sessionId"]

    payload = client.get("/admin/api/rejected-photos", headers=admin_headers).json()
    # 纯色测试图裁不出头部（_crop_head_from_photo 返回 None），face 槽无检测对象，
    # 只记录 body 检测失败；真实场景中 face 裁剪失败同样会走这条留存路径。
    kinds = sorted(row["kind"] for row in payload["rejected"])
    assert kinds == ["body"]
    for row in payload["rejected"]:
        assert row["source"].startswith("mirror")
        assert row["handoffId"] == handoff["handoffId"]
        # 下载指向镜子原图接口
        assert row["downloadUrl"].startswith(
            f"/admin/api/mirror-captures/{handoff['handoffId']}/photos/original"
        )
    labels = payload["rejected"][0]["issueLabels"]
    assert labels == ["全身不完整"]

    # 镜子原图下载链路仍可用
    download = client.get(
        f"/admin/api/mirror-captures/{handoff['handoffId']}/photos/original?download=1",
        headers=admin_headers,
    )
    assert download.status_code == 200


def test_submission_photo_attributes_visible_to_admin(monkeypatch, tmp_path: Path) -> None:
    """算法识别的肤色/脸型只进管理后台，用户端上传契约不回传。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    def attribute_inspector(image, kind):
        attributes = (
            {"skin_tone": {"label": "暖白肤", "confidence": 0.78}, "face_shape": {"label": "椭圆脸", "confidence": 0.71}}
            if kind == "face"
            else {"body_shape": {"label": "梨型", "confidence": 0.66}}
        )
        return selfit_photo.PhotoInspection(accepted=True, issues=[], attributes=attributes)

    monkeypatch.setattr(selfit_photo, "_inspector", attribute_inspector)

    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    upload = client.post(
        f"{API}/sessions/{session_id}/photos/face",
        files={"image": ("face.jpg", _jpeg_bytes("#d8c3aa"), "image/jpeg")},
    )
    assert upload.status_code == 200
    # 用户端契约不回传 attributes（不展示给用户）
    photo = upload.json()["photo"]
    assert "attributes" not in photo

    detail = client.get(f"/admin/api/submissions/{session_id}", headers=admin_headers).json()["submission"]
    face_entry = next(item for item in detail["photos"] if item["kind"] == "face")
    assert face_entry["attributes"]["skin_tone"]["label"] == "暖白肤"
    assert face_entry["attributes"]["face_shape"]["label"] == "椭圆脸"
    assert face_entry["attributes"]["skin_tone"]["confidence"] == 0.78

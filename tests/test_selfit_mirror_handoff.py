from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth
import app.selfit_mirror_handoff as mirror_handoff
import app.selfit_onboarding as onboarding
from app.main import app


def _photo_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (393, 698), "#c7a18f").save(output, "JPEG")
    return output.getvalue()


def _use_tmp_stores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(mirror_handoff, "MIRROR_DIR", tmp_path / "outputs" / "selfit_mirror")
    monkeypatch.setattr(mirror_handoff, "HANDOFF_STORE_PATH", mirror_handoff.MIRROR_DIR / "handoffs.json")
    monkeypatch.setattr(mirror_handoff, "MIRROR_ASSET_DIR", mirror_handoff.MIRROR_DIR / "assets")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_DIR", tmp_path / "outputs" / "selfit_onboarding")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_STORE_PATH", onboarding.SELFIT_ONBOARDING_DIR / "sessions.json")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_ASSET_DIR", onboarding.SELFIT_ONBOARDING_DIR / "assets")


def _login(client: TestClient, phone: str) -> dict[str, str]:
    started = client.post("/auth/phone/start", json={"phone": phone}).json()
    verified = client.post(
        "/auth/phone/verify", json={"phone": phone, "code": started["dev_code"]}
    ).json()
    return {"Authorization": f"Bearer {verified['access_token']}"}


def test_dynamic_qr_claims_suit_result_once_and_continues_at_like(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "mirror-handoff-test-secret")
    client = TestClient(app)

    created = client.post(
        "/api/v1/selfit/mirror/analyze",
        files={"photo": ("capture.jpg", _photo_bytes(), "image/jpeg")},
    )
    payload = created.json()
    token = payload["qrImageUrl"].split("/handoffs/", 1)[1].rsplit("/qr", 1)[0]

    qr = client.get(payload["qrImageUrl"])
    before = client.get(payload["statusUrl"]).json()["handoff"]
    user_a = _login(client, "13800000801")
    claimed = client.post(
        f"/api/v1/selfit/mirror/handoffs/{token}/claim", headers=user_a
    )
    claimed_again = client.post(
        f"/api/v1/selfit/mirror/handoffs/{token}/claim", headers=user_a
    )
    after = client.get(payload["statusUrl"]).json()["handoff"]

    assert created.status_code == 201
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content.startswith(b"\x89PNG")
    assert before["status"] == "pending"
    assert claimed.status_code == 200
    assert claimed.json()["nextStep"] == "like"
    assert claimed.json()["session"]["sessionId"] == claimed_again.json()["session"]["sessionId"]
    assert after["status"] == "claimed"

    handoff_store = mirror_handoff.HANDOFF_STORE_PATH.read_text(encoding="utf-8")
    assert token not in handoff_store
    onboarding_data = json.loads(onboarding.SELFIT_ONBOARDING_STORE_PATH.read_text(encoding="utf-8"))
    session = onboarding_data["sessions"][0]
    assert session["user_id"].startswith("u_")
    assert session["source"] == "mirror_handoff"
    assert session["suit_completed_at"]
    assert session["mirror_analysis"]["result"]["image_id"]
    assert session["mirror_assets"]["original"]["role"] == "suit_input"
    assert session["mirror_assets"]["retouched"]["role"] == "mirro_preview"
    assert session["suit_input_asset_id"] == session["mirror_assets"]["original"]["asset_id"]
    assert session["mirror_preview_asset_id"] == session["mirror_assets"]["retouched"]["asset_id"]
    assert "result_summary" in session["mirror_analysis"]["result"]
    restored = client.get(
        f"/api/v1/selfit/sessions/{session['session_id']}", headers=user_a
    ).json()["session"]
    assert "photos" in restored["completedSteps"]


def test_dynamic_qr_supports_phone_direct_login_for_roadshow(monkeypatch, tmp_path: Path) -> None:
    """路演链路：扫码 → 免验证码手机号登录 → 领取镜子结果 → 跳 like。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "mirror-handoff-test-secret")
    client = TestClient(app)

    created = client.post(
        "/api/v1/selfit/mirror/analyze",
        files={"photo": ("capture.jpg", _photo_bytes(), "image/jpeg")},
    ).json()
    token = created["qrImageUrl"].split("/handoffs/", 1)[1].rsplit("/qr", 1)[0]

    direct = client.post(
        "/auth/phone/direct",
        json={"phone": "13800000811"},
        headers={"x-real-ip": "198.51.100.30"},
    )
    claimed = client.post(
        f"/api/v1/selfit/mirror/handoffs/{token}/claim",
        headers={"Authorization": f"Bearer {direct.json()['access_token']}"},
    )

    assert direct.status_code == 200
    assert direct.json()["user"]["phone_e164"] == "+8613800000811"
    assert claimed.status_code == 200
    assert claimed.json()["nextStep"] == "like"
    session_id = claimed.json()["session"]["sessionId"]
    restored = client.get(
        f"/api/v1/selfit/sessions/{session_id}",
        headers={"Authorization": f"Bearer {direct.json()['access_token']}"},
    ).json()["session"]
    assert "photos" in restored["completedSteps"]
    onboarding_data = json.loads(onboarding.SELFIT_ONBOARDING_STORE_PATH.read_text(encoding="utf-8"))
    session = onboarding_data["sessions"][0]
    assert session["user_id"] == direct.json()["user"]["user_id"]
    assert session["suit_input_asset_id"] == session["mirror_assets"]["original"]["asset_id"]


QA_BODY_PHOTO = Path(__file__).resolve().parents[1] / "qa_photos" / "body" / "body_01.jpg"


def test_claim_hydrates_suit_photos_from_mirror_capture(monkeypatch, tmp_path: Path) -> None:
    """镜子全身照应回填为 suit 的 body 输入，并裁出头部作为 face 输入。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "mirror-handoff-test-secret")
    client = TestClient(app)

    created = client.post(
        "/api/v1/selfit/mirror/analyze",
        files={"photo": ("capture.jpg", QA_BODY_PHOTO.read_bytes(), "image/jpeg")},
    )
    payload = created.json()
    token = payload["qrImageUrl"].split("/handoffs/", 1)[1].rsplit("/qr", 1)[0]
    user = _login(client, "13800000804")
    claimed = client.post(f"/api/v1/selfit/mirror/handoffs/{token}/claim", headers=user)

    assert created.status_code == 201
    assert claimed.status_code == 200
    session_id = claimed.json()["session"]["sessionId"]
    onboarding_data = json.loads(onboarding.SELFIT_ONBOARDING_STORE_PATH.read_text(encoding="utf-8"))
    session = next(record for record in onboarding_data["sessions"] if record["session_id"] == session_id)
    photos = session.get("photos") or {}
    assert photos.get("body", {}).get("status") == "accepted"
    assert photos["body"].get("source") == "mirror"
    assert photos.get("face", {}).get("status") == "accepted"
    assert photos["face"].get("source") == "mirror_head_crop"
    # 大头照是全身照裁出来的方图，尺寸小于原图
    assert photos["face"]["width"] == photos["face"]["height"]
    assert photos["face"]["width"] < photos["body"]["width"]
    asset_dir = onboarding.SELFIT_ONBOARDING_ASSET_DIR / session_id
    assert list(asset_dir.glob("asset_body_*.jpg"))
    assert list(asset_dir.glob("asset_face_*.jpg"))


def test_claim_rejects_anonymous_and_second_user(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "mirror-handoff-test-secret")
    client = TestClient(app)
    payload = client.post(
        "/api/v1/selfit/mirror/analyze",
        files={"photo": ("capture.jpg", _photo_bytes(), "image/jpeg")},
    ).json()
    token = payload["qrImageUrl"].split("/handoffs/", 1)[1].rsplit("/qr", 1)[0]

    anonymous = client.post(f"/api/v1/selfit/mirror/handoffs/{token}/claim")
    first = client.post(
        f"/api/v1/selfit/mirror/handoffs/{token}/claim",
        headers=_login(client, "13800000802"),
    )
    second = client.post(
        f"/api/v1/selfit/mirror/handoffs/{token}/claim",
        headers=_login(client, "13800000803"),
    )

    assert anonymous.status_code == 401
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "mirror.handoff_claimed"


def test_color_grade_save_is_immediately_effective_and_versioned(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    initial = client.get("/api/v1/selfit/mirror/color-grade")
    parameters = initial.json()["parameters"]
    parameters["exposure"] = 0.12
    parameters["highlights"] = -0.18
    parameters["hsl"]["orange"]["lightness"] = 0.06
    saved = client.put(
        "/api/v1/selfit/mirror/color-grade",
        headers={"If-Match": str(initial.json()["version"])},
        json={"parameters": parameters},
    )
    effective = client.get("/api/v1/selfit/mirror/color-grade")

    assert initial.status_code == 200
    assert saved.status_code == 200
    assert saved.json()["version"] == initial.json()["version"] + 1
    assert effective.json() == saved.json()
    assert effective.json()["parameters"]["exposure"] == 0.12
    assert effective.json()["parameters"]["hsl"]["orange"]["lightness"] == 0.06
    stored = json.loads((mirror_handoff.MIRROR_DIR / "color_grade.json").read_text(encoding="utf-8"))
    assert stored["history"][0]["version"] == initial.json()["version"]


def test_color_grade_rejects_out_of_range_and_stale_updates(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    initial = client.get("/api/v1/selfit/mirror/color-grade").json()
    invalid = json.loads(json.dumps(initial["parameters"]))
    invalid["exposure"] = 2

    rejected = client.put(
        "/api/v1/selfit/mirror/color-grade",
        headers={"If-Match": str(initial["version"])},
        json={"parameters": invalid},
    )
    saved = client.put(
        "/api/v1/selfit/mirror/color-grade",
        headers={"If-Match": str(initial["version"])},
        json={"parameters": initial["parameters"]},
    )
    stale = client.put(
        "/api/v1/selfit/mirror/color-grade",
        headers={"If-Match": str(initial["version"])},
        json={"parameters": initial["parameters"]},
    )

    assert rejected.status_code == 422
    assert saved.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "mirror.color_grade_conflict"


def test_mirror_capture_keeps_original_and_retouched_assets_separate(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    original = _photo_bytes()
    retouched_output = io.BytesIO()
    Image.new("RGB", (393, 698), "#d5ad9d").save(retouched_output, "JPEG")

    created = client.post(
        "/api/v1/selfit/mirror/analyze",
        files={
            "original": ("original.jpg", original, "image/jpeg"),
            "retouched": ("retouched.jpg", retouched_output.getvalue(), "image/jpeg"),
        },
        data={"metadata": json.dumps({"colorGrade": {"configId": "mirro_color_grade", "version": 3}})},
    )

    assert created.status_code == 201
    data = json.loads(mirror_handoff.HANDOFF_STORE_PATH.read_text(encoding="utf-8"))
    handoff = data["handoffs"][0]
    assert handoff["assets"]["original"]["role"] == "suit_input"
    assert handoff["assets"]["retouched"]["role"] == "mirro_preview"
    assert handoff["assets"]["retouched"]["derived_from"] == handoff["assets"]["original"]["asset_id"]
    assert handoff["assets"]["retouched"]["color_grade"]["version"] == 3
    assert handoff["asset_path"] == handoff["assets"]["original"]["asset_path"]
    assert Path(handoff["assets"]["original"]["asset_path"]).read_bytes() == original
    assert Path(handoff["assets"]["retouched"]["asset_path"]).read_bytes() == retouched_output.getvalue()

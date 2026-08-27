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
    assert "result_summary" in session["mirror_analysis"]["result"]
    restored = client.get(
        f"/api/v1/selfit/sessions/{session['session_id']}", headers=user_a
    ).json()["session"]
    assert "photos" in restored["completedSteps"]


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

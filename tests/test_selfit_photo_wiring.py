"""selfit onboarding 照片算法接入的端到端测试。

覆盖三层：
1. attribute_inspector：真实 fixture → 契约枚举 / 属性标签；
2. 路由层：真实大头照/全身照上传后的接受与拒绝行为；
3. 属性落库：accepted 照片的推断标签写入会话记录，供报告任务消费。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.selfit_onboarding as selfit_onboarding
import app.selfit_photo as selfit_photo
from app.main import app

API = "/api/v1/selfit"
FIXTURE_IMAGES = Path(__file__).resolve().parent / "fixtures" / "images"
FIXTURE_MODELS = Path(__file__).resolve().parent / "fixtures" / "tryon_models"


def _use_tmp_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store_dir = tmp_path / "outputs" / "selfit_onboarding"
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_DIR", store_dir)
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_STORE_PATH", store_dir / "sessions.json")
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_ASSET_DIR", store_dir / "assets")


def _create_session(client: TestClient) -> str:
    response = client.post(f"{API}/sessions", json={"schemaVersion": "selfit-onboarding-v1"})
    assert response.status_code == 201
    return response.json()["session"]["sessionId"]


def _upload(client: TestClient, session_id: str, kind: str, path: Path) -> dict:
    with path.open("rb") as fh:
        response = client.post(f"{API}/sessions/{session_id}/photos/{kind}", files={"image": (path.name, fh)})
    assert response.status_code == 200
    return response.json()


def _stored_session(tmp_path: Path, session_id: str) -> dict:
    store = json.loads((tmp_path / "outputs" / "selfit_onboarding" / "sessions.json").read_text(encoding="utf-8"))
    return next(record for record in store["sessions"] if record["session_id"] == session_id)


# ---------------------------------------------------------------------------
# attribute_inspector 单元行为
# ---------------------------------------------------------------------------

def test_inspector_accepts_clear_face_with_attributes() -> None:
    image = Image.open(FIXTURE_IMAGES / "real_warm_indoor_light_no_card.jpg")
    inspection = selfit_photo.attribute_inspector(image, "face")
    assert inspection.accepted is True
    assert inspection.issues == []
    assert inspection.attributes["skin_tone"]["label"] in {"冷白肤", "暖白肤", "中性自然肤", "暖黄肤", "橄榄肤", "小麦色"}
    assert inspection.attributes["face_shape"]["label"] in {"椭圆脸", "圆脸", "方脸", "心形脸", "菱形脸"}


def test_inspector_rejects_bangs_forehead() -> None:
    image = Image.open(FIXTURE_IMAGES / "real_bangs_forehead.jpg")
    inspection = selfit_photo.attribute_inspector(image, "face")
    assert inspection.accepted is False
    assert inspection.issues == [selfit_photo.ISSUE_BANGS_FOREHEAD]


def test_inspector_rejects_multiple_people() -> None:
    image = Image.open(FIXTURE_IMAGES / "portrait_multi_face.jpg")
    inspection = selfit_photo.attribute_inspector(image, "face")
    assert inspection.accepted is False
    assert selfit_photo.ISSUE_MULTIPLE_PEOPLE in inspection.issues


def test_inspector_rejects_non_person_face() -> None:
    image = Image.open(FIXTURE_IMAGES / "portrait_non_person.png")
    inspection = selfit_photo.attribute_inspector(image, "face")
    assert inspection.accepted is False
    assert selfit_photo.ISSUE_FACE_NOT_FOUND in inspection.issues


def test_inspector_accepts_full_body_with_body_shape() -> None:
    image = Image.open(FIXTURE_MODELS / "female_slim_1.png")
    inspection = selfit_photo.attribute_inspector(image, "body")
    assert inspection.accepted is True
    assert inspection.attributes["body_shape"]["label"] in {"梨型", "倒三角型", "沙漏型", "矩型", "苹果型"}


def test_inspector_rejects_face_photo_as_body() -> None:
    image = Image.open(FIXTURE_IMAGES / "real_clear_glasses.jpg")
    inspection = selfit_photo.attribute_inspector(image, "body")
    assert inspection.accepted is False
    assert selfit_photo.ISSUE_BODY_NOT_COMPLETE in inspection.issues


# ---------------------------------------------------------------------------
# 路由层端到端
# ---------------------------------------------------------------------------

def test_upload_real_face_photo_accepted_and_attributes_stored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "face", FIXTURE_IMAGES / "real_warm_indoor_light_no_card.jpg")
    photo = payload["photo"]
    assert photo["status"] == "accepted"
    assert photo["code"] == "photo.accepted"
    assert photo["assetId"].startswith("asset_face_")

    stored = _stored_session(tmp_path, session_id)
    attributes = stored["photos"]["face"]["attributes"]
    assert attributes["skin_tone"]["label"]
    assert attributes["face_shape"]["label"]


def test_upload_bangs_photo_rejected_with_actionable_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "face", FIXTURE_IMAGES / "real_bangs_forehead.jpg")
    photo = payload["photo"]
    assert photo["status"] == "rejected"
    assert photo["code"] == "photo.bangs_forehead"
    assert photo["issues"] == ["bangs_forehead"]
    assert "刘海" in photo["message"]
    assert photo["assetId"] is None

    stored = _stored_session(tmp_path, session_id)
    assert stored["photos"]["face"]["status"] == "rejected"
    assert "attributes" not in stored["photos"]["face"]


def test_upload_full_body_photo_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "body", FIXTURE_MODELS / "female_slim_1.png")
    photo = payload["photo"]
    assert photo["status"] == "accepted"

    stored = _stored_session(tmp_path, session_id)
    assert stored["photos"]["body"]["attributes"]["body_shape"]["label"]


def test_upload_face_as_body_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "body", FIXTURE_IMAGES / "real_clear_glasses.jpg")
    photo = payload["photo"]
    assert photo["status"] == "rejected"
    assert photo["code"] == "photo.body_not_complete"
    assert "全身" in photo["message"]

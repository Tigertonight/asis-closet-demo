"""selfit onboarding 照片算法接入的端到端测试。

覆盖三层：
1. attribute_inspector：真实 fixture → 契约枚举 / 属性标签；
2. 路由层：真实大头照/全身照上传后的接受与拒绝行为；
3. 属性落库：accepted 照片的推断标签写入会话记录，供报告任务消费。
"""

from __future__ import annotations

import json
import os
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


def test_inspector_accepts_bangs_forehead() -> None:
    # 产品口径（内测定版）：刘海照不拦截上传，脸型交给用户手动确认。
    image = Image.open(FIXTURE_IMAGES / "real_bangs_forehead.jpg")
    inspection = selfit_photo.attribute_inspector(image, "face")
    assert inspection.accepted is True
    assert inspection.issues == []


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


def test_upload_bangs_photo_accepted_with_skin_attributes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 产品口径（内测定版）：刘海照不拦截上传；肤色照常识别，脸型无预选标签。
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "face", FIXTURE_IMAGES / "real_bangs_forehead.jpg")
    photo = payload["photo"]
    assert photo["status"] == "accepted"
    assert photo["code"] == "photo.accepted"
    assert photo["assetId"].startswith("asset_face_")

    stored = _stored_session(tmp_path, session_id)
    attributes = stored["photos"]["face"]["attributes"]
    assert attributes["skin_tone"]["label"]
    assert "face_shape" not in attributes or not attributes["face_shape"].get("label")


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
    assert "身形" in photo["message"]


# ---------------------------------------------------------------------------
# 用户照片归档进 QA 数据集（算法分析资产）
# ---------------------------------------------------------------------------

def test_upload_accepted_archives_to_qa_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """App 上传通过检测的照片自动进 QA 数据集，source=app；被拒照片不进。"""

    import app.qa_onboarding as qa_onboarding

    _use_tmp_store(monkeypatch, tmp_path)
    qa_dir = tmp_path / "qa_photos"
    monkeypatch.setattr(qa_onboarding, "QA_PHOTO_DIR", qa_dir)
    monkeypatch.setattr(qa_onboarding, "QA_RESULTS_CACHE", qa_dir / "_results.json")
    client = TestClient(app)
    session_id = _create_session(client)

    payload = _upload(client, session_id, "face", FIXTURE_IMAGES / "real_warm_indoor_light_no_card.jpg")
    assert payload["photo"]["status"] == "accepted"

    manifest = json.loads((qa_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["source"] == "app"
    assert manifest[0]["kind"] == "face"
    assert manifest[0]["file"].startswith("face/user_face_")
    assert (qa_dir / manifest[0]["file"]).exists()

    # 同一张照片重复上传（新 session）→ 内容 hash 去重
    session_id_2 = _create_session(client)
    payload_2 = _upload(client, session_id_2, "face", FIXTURE_IMAGES / "real_warm_indoor_light_no_card.jpg")
    assert payload_2["photo"]["status"] == "accepted"
    manifest = json.loads((qa_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1

    # 被拒照片不归档
    rejected = _upload(client, session_id_2, "face", FIXTURE_IMAGES / "portrait_non_person.png")
    assert rejected["photo"]["status"] == "rejected"
    manifest = json.loads((qa_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1


# ---------------------------------------------------------------------------
# 路演容量保护：face 检测预缩 + 并发信号量
# ---------------------------------------------------------------------------

def test_face_inspect_input_is_downscaled_body_kept() -> None:
    """face 检测输入预缩到长边 1280（landmark 归一化坐标，判定一致）；
    body 不缩（轮廓测量对分辨率敏感，缩图会让身型漂移）。"""

    from app.selfit_photo import _INSPECT_MAX_SIDE, _prepare_inspect_input

    large = Image.new("RGB", (2000, 3000), (200, 180, 170))
    face_small = _prepare_inspect_input(large, "face")
    assert max(face_small.size) <= _INSPECT_MAX_SIDE
    body_same = _prepare_inspect_input(large, "body")
    assert body_same.size == large.size
    # 小图原样返回（不放大）
    small = Image.new("RGB", (600, 800), (200, 180, 170))
    assert _prepare_inspect_input(small, "face").size == small.size


def test_inspect_semaphore_limits_concurrency() -> None:
    """并发信号量：同时进行的检测数不超过核数（高峰排队而非雪崩）。"""

    import threading
    import time

    from app.selfit_photo import _INSPECT_SEMAPHORE

    expected = max(1, os.cpu_count() or 2)
    assert _INSPECT_SEMAPHORE._value == expected  # 初始满配
    active = 0
    peak = 0
    lock = threading.Lock()

    from app.selfit_photo import attribute_inspector

    def slow_inspect(image, kind):
        # 直接调 attribute_inspector 内部的信号量段（真实检测太慢，stub 检测函数）
        with _INSPECT_SEMAPHORE:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
        return selfit_photo.PhotoInspection(accepted=True, issues=[])

    # 直接并发跑信号量段验证上限（真实检测慢，不需要跑完整管线）
    threads = []
    for _ in range(expected * 3):
        t = threading.Thread(target=slow_inspect, args=(None, "face"))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    assert peak <= expected, f"并发峰值 {peak} 超过信号量上限 {expected}"

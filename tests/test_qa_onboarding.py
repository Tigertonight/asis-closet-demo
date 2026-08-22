"""QA 页面（/qa/onboarding-attributes）的渲染测试。

路由依赖真实模型与 qa_photos 素材，测试中 stub 掉分析层，只验证页面结构与渲染。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.qa_onboarding as qa_onboarding
from app.main import app


def _fake_entry(kind: str = "face") -> dict:
    attribute = {
        "status": "pass",
        "label": "自然色" if kind == "face" else "梨型",
        "confidence": 0.72,
        "issues": [],
        "evidence": {"l_star": 63.2, "ita_deg": 44.1} if kind == "face" else {"measurements": {"shoulder_width": 200.0, "hip_width": 240.0, "waist_width": 180.0}, "classification": {"ratios": {"hip_over_shoulder": 1.2, "waist_over_hip": 0.75}}},
    }
    attributes = {"skin_tone": attribute, "face_shape": {**attribute, "label": "椭圆脸", "candidates": [{"label": "椭圆脸", "score": 0.6}, {"label": "圆脸", "score": 0.3}]}} if kind == "face" else {"body_shape": attribute}
    return {
        "item": {"file": f"{kind}/{kind}_01.jpg", "kind": kind, "source_url": "https://example.com", "alt": "sample"},
        "result": {"status": "pass", "confidence": 0.72, "issues": [{"code": "photo.color_cast", "message": "照片整体有偏色", "suggestion": "..."}], "attributes": attributes},
    }


def test_qa_page_renders_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [_fake_entry("face"), _fake_entry("body")])
    client = TestClient(app)
    response = client.get("/qa/onboarding-attributes")
    assert response.status_code == 200
    text = response.text
    assert "onboarding 属性识别 QA" in text
    assert "自然色" in text and "椭圆脸" in text and "梨型" in text
    assert "photo.color_cast" in text
    assert "重新分析" in text


def test_qa_page_empty_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [])
    client = TestClient(app)
    response = client.get("/qa/onboarding-attributes")
    assert response.status_code == 200
    assert "共 0 张" in response.text


# ---------------------------------------------------------------------------
# 数据标注
# ---------------------------------------------------------------------------

MANIFEST = [
    {"file": "face/face_01.jpg", "kind": "face", "source_url": "", "alt": ""},
    {"file": "body/body_01.jpg", "kind": "body", "source_url": "", "alt": ""},
]


def _setup_annotation_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(qa_onboarding, "QA_ANNOTATIONS_PATH", tmp_path / "annotations.json")
    monkeypatch.setattr(qa_onboarding, "_load_manifest", lambda: MANIFEST)
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [_fake_entry("face"), _fake_entry("body")])
    monkeypatch.setattr(qa_onboarding, "_ensure_overlays", lambda entries, refresh=False: {})


def _create_task(client: TestClient, name: str = "第一轮标注") -> str:
    response = client.post("/qa/annotations/tasks", data={"name": name}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert "tab=annotate&task=ann_" in location
    return location.split("task=", 1)[1]


def test_create_annotation_task_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = TestClient(app)
    task_id = _create_task(client)

    list_page = client.get("/qa/onboarding-attributes?tab=annotate")
    assert list_page.status_code == 200
    assert "第一轮标注" in list_page.text
    assert "详情" in list_page.text

    detail_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}")
    assert detail_page.status_code == 200
    assert "第一轮标注" in detail_page.text
    assert "保存标注" in detail_page.text
    assert "一键对比" in detail_page.text


def test_batch_save_and_clear_annotations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = TestClient(app)
    task_id = _create_task(client)

    ok = client.post(
        f"/qa/annotations/{task_id}/batch",
        json={"annotations": {"face/face_01.jpg": {"skin_tone": "自然色", "face_shape": "椭圆脸"}, "body/body_01.jpg": {"body_shape": "梨型"}}},
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True
    stored = json.loads((tmp_path / "annotations.json").read_text(encoding="utf-8"))
    assert stored["tasks"][0]["annotations"]["face/face_01.jpg"]["face_shape"] == "椭圆脸"

    bad_value = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/face_01.jpg": {"skin_tone": "蜜糖色"}}})
    assert bad_value.status_code == 422
    bad_attr = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"body/body_01.jpg": {"skin_tone": "自然色"}}})
    assert bad_attr.status_code == 422
    missing_file = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/none.jpg": {"skin_tone": "自然色"}}})
    assert missing_file.status_code == 404

    # 整体替换语义：再次提交只含一条，其余视为清除
    cleared = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/face_01.jpg": {"skin_tone": "自然白"}}})
    assert cleared.status_code == 200
    stored = json.loads((tmp_path / "annotations.json").read_text(encoding="utf-8"))
    assert stored["tasks"][0]["annotations"] == {"face/face_01.jpg": {"skin_tone": "自然白"}}


def test_diff_filter_shows_only_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = TestClient(app)
    task_id = _create_task(client)

    # face_01 算法识别为 自然色/椭圆脸：标对一个、标错一个；body_01 标对
    client.post(
        f"/qa/annotations/{task_id}/batch",
        json={"annotations": {"face/face_01.jpg": {"skin_tone": "自然色", "face_shape": "方脸"}, "body/body_01.jpg": {"body_shape": "梨型"}}},
    )

    all_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}")
    assert "不一致 1" in all_page.text
    assert "算法：椭圆脸 ≠ 标注：方脸" in all_page.text

    diff_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}&diff=1")
    assert "face/face_01.jpg" in diff_page.text
    assert "body/body_01.jpg" not in diff_page.text


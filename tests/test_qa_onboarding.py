"""QA 页面（/qa/onboarding-attributes）的渲染测试。

路由依赖真实模型与 qa_photos 素材，测试中 stub 掉分析层，只验证页面结构与渲染。
"""

from __future__ import annotations

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

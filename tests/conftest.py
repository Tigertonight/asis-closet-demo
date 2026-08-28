from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _disable_rate_limit_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "1")


@pytest.fixture(autouse=True)
def _isolate_qa_photo_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """QA 数据集目录隔离到临时目录：上传 accepted 会归档进 qa_photos，
    不隔离的话测试会把 user_*.jpg 写进真实数据集。"""

    import app.qa_onboarding as qa_onboarding

    qa_dir = tmp_path / "qa_photos"
    monkeypatch.setattr(qa_onboarding, "QA_PHOTO_DIR", qa_dir)
    monkeypatch.setattr(qa_onboarding, "QA_RESULTS_CACHE", qa_dir / "_results.json")
    monkeypatch.setattr(qa_onboarding, "QA_OVERLAY_DIR", qa_dir / "_overlays")
    monkeypatch.setattr(qa_onboarding, "QA_ANNOTATIONS_PATH", qa_dir / "_annotations.json")

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _disable_rate_limit_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASIS_DISABLE_RATE_LIMIT", "1")

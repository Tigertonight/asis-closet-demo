#!/usr/bin/env python3
"""Precompute the four bundled samples with the real photo algorithm."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import selfit_onboarding, selfit_samples  # registers the configured inspector

if __name__ == "__main__":
    print(json.dumps(selfit_samples.warm_samples(), ensure_ascii=False, indent=2))

"""selfit application package and legacy environment compatibility."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def _promote_legacy_environment() -> None:
    """Let existing deployments boot while selfit-prefixed settings roll out."""

    prefix_pairs = (
        ("ORI_", "SELFIT_"),
        ("STYLIST_ORI_", "STYLIST_SELFIT_"),
        ("OPENCLAW_ORI_", "OPENCLAW_SELFIT_"),
    )
    for legacy_name, value in tuple(os.environ.items()):
        for legacy_prefix, selfit_prefix in prefix_pairs:
            if legacy_name.startswith(legacy_prefix):
                selfit_name = f"{selfit_prefix}{legacy_name[len(legacy_prefix):]}"
                os.environ.setdefault(selfit_name, value)
                break


_promote_legacy_environment()

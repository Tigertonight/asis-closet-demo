"""Versioned editorial overlay. Asset approval is not outfit/style approval.

Legacy content may continue serving while it is reviewed, but only the exact
audited revision is grandfathered. New/changed recipes fail closed. Original
records and image files remain available for saved-look/history resolution.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

CURATION_PATH = Path(__file__).resolve().parent / "static/selfit/data/content-curation.v1.json"
GATES = ("technical", "aesthetic", "persona", "context")


def record_fingerprint(record: dict[str, Any]) -> str:
    # Everything except workflow history participates, including image URL,
    # recipe version, roles, context and metadata, not just garment IDs.
    value = {k: v for k, v in record.items() if k not in {"annotation", "quality_review", "curation", "imageUrl"}}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def review_is_current(record: dict[str, Any]) -> bool:
    review = record.get("quality_review") or {}
    return review.get("record_fingerprint") == record_fingerprint(record) and all(
        (review.get(gate) or {}).get("status") == "passed"
        and (review.get(gate) or {}).get("reviewer")
        and (review.get(gate) or {}).get("evidence")
        for gate in GATES
    )


@lru_cache(maxsize=4)
def _read_overlay(path: str, stamp: int) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.get("schemaVersion") != "1.0":
            return {}
        for section in ("garments", "outfits"):
            entries = value.get(section)
            if not isinstance(entries, dict):
                return {}
            for entry in entries.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("patch"), dict) or not isinstance(entry.get("source_fingerprint"), str):
                    return {}
                if section == "outfits" and entry.get("status") not in {"legacy_allowed", "approved", "hold", "alias", "pending"}:
                    return {}
        return value
    except (OSError, ValueError, AttributeError):
        return {}


def curation_stamp() -> int:
    try:
        return CURATION_PATH.stat().st_mtime_ns
    except OSError:
        return 0


def load_curation() -> dict[str, Any]:
    return _read_overlay(str(CURATION_PATH), curation_stamp())


def is_generated_outfit(record: dict[str, Any]) -> bool:
    return bool(record.get("garment_ids")) and "/content_v2/" in str((record.get("assets") or {}).get("image_url", ""))


def recommendable(record: dict[str, Any]) -> bool:
    curation = record.get("curation")
    return not curation or curation.get("status") in {"legacy_allowed", "approved"}


def apply_curation(data: dict[str, Any], overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    overlay = load_curation() if overlay is None else overlay
    result = copy.deepcopy(data)
    for section in ("garments", "outfits"):
        for record in result.get(section, []):
            if not isinstance(record, dict):
                continue
            entry = (overlay.get(section) or {}).get(record.get("id"))
            if entry and entry.get("source_fingerprint") == record_fingerprint(record):
                record.update(copy.deepcopy(entry.get("patch") or {}))
                if section == "outfits":
                    record["curation"] = {key: copy.deepcopy(value) for key, value in entry.items() if key not in {"patch", "source_fingerprint"}}
            elif section == "outfits" and is_generated_outfit(record):
                record["curation"] = {
                    "status": "approved" if review_is_current(record) else "pending",
                    "reason_codes": ["current_evidence" if review_is_current(record) else "new_or_changed_recipe_requires_review"],
                }
    counts = Counter((row.get("curation") or {}).get("status", "unmanaged") for row in result.get("outfits", []))
    result["curation_summary"] = {"version": overlay.get("version"), "status_counts": dict(counts),
                                 "recommendable": sum(recommendable(row) for row in result.get("outfits", [])),
                                 "note": "legacy_allowed is continuity, not designer or blind-review approval"}
    return result


def publication_errors(record: dict[str, Any]) -> list[str]:
    """New publications need separate, revision-bound evidence, not a CLI flag."""
    if not review_is_current(record):
        return [f"missing or stale four-gate review: {record.get('id')}"]
    return []


def publication_status(record: dict[str, Any]) -> str:
    entry = (load_curation().get("outfits") or {}).get(record.get("id")) or {}
    if entry.get("source_fingerprint") == record_fingerprint(record):
        return str(entry.get("status") or "pending")
    return "approved" if review_is_current(record) else "pending"

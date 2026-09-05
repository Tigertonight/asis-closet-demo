"""Revision-bound AI observations. Missing vision evidence never means approved."""
from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from app.selfit_content_quality import record_fingerprint

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "app/data/recommendation-visual.v1.json"
EXPRESSIONS = frozenset({"easy", "typical", "explore", "experimental"})
FIELDS = {
    "garments": {"category", "subcategory", "neckline", "sleeve", "length", "volume", "construction", "pattern", "decoration", "material_appearance"},
    "outfits": {"structure", "layering", "formality", "wearability", "expression", "seasons", "scenes", "axes", "persona_scores"},
}


@lru_cache(maxsize=4096)
def _asset_sha(path, stamp, size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset_sha(url):
    if not isinstance(url, str) or not url.startswith("/static/"):
        return None
    path = (ROOT / "app" / url.lstrip("/")).resolve()
    if not path.is_relative_to(ROOT / "app/static") or not path.is_file():
        return None
    stat = path.stat()
    return _asset_sha(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _load(path, stamp):
    try:
        data = json.loads(Path(path).read_text())
        if isinstance(data, dict) and data.get("schema_version") == 1:
            return data
    except (OSError, ValueError):
        pass
    return {"garments": {}, "outfits": {}, "status": "pending_vision"}


def load_visual():
    path = Path(os.getenv("SELFIT_RECOMMENDATION_VISUAL_PATH", str(DEFAULT_PATH)))
    return _load(str(path), path.stat().st_mtime_ns if path.exists() else 0)


def valid_observation(record, observation, image_url, section=None):
    if not isinstance(observation, dict):
        return False
    confidence = observation.get("confidence")
    fields = observation.get("observations")
    if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not math.isfinite(confidence) or not .75 <= confidence <= 1
            or not isinstance(fields, dict)):
        return False
    if section and not FIELDS[section].issubset(fields):
        return False
    if section == "outfits":
        if fields.get("structure") not in {"pants", "skirt", "dress"} or fields.get("expression") not in EXPRESSIONS:
            return False
        for name in ("seasons", "scenes"):
            if fields.get(name) is not None and (not isinstance(fields[name], list) or not all(isinstance(v, str) for v in fields[name])):
                return False
        for name in ("axes", "persona_scores"):
            values = fields.get(name)
            if not isinstance(values, dict) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= (100 if name == "axes" else 1) for v in values.values()):
                return False
    return (observation.get("status") == "ai_candidate"
            and observation.get("source_kind") in {"vision_model", "codex_visual_review"} and observation.get("model")
            and observation.get("prompt_version") and observation.get("evidence")
            and observation.get("record_fingerprint") == record_fingerprint(record)
            and observation.get("asset_sha256") == asset_sha(image_url)
            and observation.get("asset_sha256") is not None)


def attach_visual(catalog, garments, outfits, visual=None):
    visual = load_visual() if visual is None else visual
    if not isinstance(visual, dict) or any(not isinstance(visual.get(k, {}), dict) for k in ("garments", "outfits")):
        visual = {}
    gs = {g["id"]: g for g in garments}
    os_by_id = {o["id"]: o for o in outfits}
    accepted, held = [], {}
    for outfit in catalog:
        oid = outfit["outfit_id"]
        raw = os_by_id.get(oid)
        observation = visual.get("outfits", {}).get(oid)
        if not raw or not valid_observation(raw, observation, outfit.get("cover_path"), "outfits"):
            held[oid] = "outfit_visual_pending_or_stale"
            continue
        verified = []
        for item in outfit["items"]:
            gid = item["item_id"]
            g = gs.get(gid)
            go = visual.get("garments", {}).get(gid)
            if not g or not valid_observation(g, go, (g.get("assets") or {}).get("image_url"), "garments"):
                break
            verified.append({**item, "visual": go["observations"], "color_evidence": g.get("color_evidence") or {}})
        if len(verified) != len(outfit["items"]):
            held[oid] = "garment_visual_pending_or_stale"
            continue
        accepted.append({**outfit, "items": verified, "visual": observation["observations"],
                         "visual_evidence": observation["evidence"], "visual_confidence": observation["confidence"]})
    return accepted, held

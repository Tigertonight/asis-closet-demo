"""Account-owned, read-only recommendation context. Never trusts URL personas."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

PALETTES = {"mono": "黑白灰", "earth": "大地色", "ocean": "海洋蓝", "jewel": "宝石色", "bright": "明亮色", "pastel": "柔粉浅彩"}
AXES = {"shape", "energy", "trend"}
PERSONAS = {"mute", "iced", "heir", "ease", "melt", "wabi", "flou", "neon", "edge", "bolt", "film", "jade", "loop", "noir", "void", "oops"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validation_enabled(user_id):
    enabled = os.getenv("SELFIT_RECOMMENDATION_V3_ENABLED", "0").lower() in {"1", "true"}
    allowlist = {s.strip() for s in os.getenv("SELFIT_RECOMMENDATION_V3_USERS", "").split(",") if s.strip()}
    return enabled and user_id in allowlist  # no wildcard / query-string activation


def resolve_profile(user_id, store=None, preferences=None):
    if store is None:
        from app.selfit_onboarding import _load_store
        store = _load_store()
    if preferences is None:
        from app.closet import get_user_preferences
        preferences = get_user_preferences()
    reports = [r for r in store.get("reports", []) if r.get("user_id") == user_id
               and (r.get("data") or {}).get("typeId", "").lower() in PERSONAS]
    report = max(reports, key=lambda r: (str(r.get("created_at") or ""), r.get("report_id", "")), default={})
    session = next((s for s in store.get("sessions", []) if report.get("session_id")
                    and s.get("session_id") == report["session_id"] and s.get("user_id") == user_id), {})
    original = session.get("preferences") or {}
    explicit = preferences.get("recommendation") or {}
    palette = explicit.get("palette") if explicit.get("palette") in PALETTES else original.get("palette")
    palette = palette if palette in PALETTES else None
    axes = {k: v for k, v in (original.get("axes") or {}).items()
            if k in AXES and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100}
    profile = {
        "persona_id": (report.get("data") or {}).get("typeId", "").lower() or None,
        "palette": palette, "axes": axes,
        "palette_source": "explicit_preference" if explicit.get("palette") in PALETTES else "onboarding" if palette else "persona_template_fallback",
        "excluded_categories": explicit.get("excluded_categories", []),
        "preferred_categories": explicit.get("preferred_categories", []),
        "scene": explicit.get("scene"), "report_id": report.get("report_id"),
        "template_colors": (report.get("data") or {}).get("colors", {}),
    }
    profile["version"] = digest(profile)
    profile["validation_enabled"] = validation_enabled(user_id)
    return profile


def preview_profile(profile, context, persona):
    """Separate request-only override; it is never persisted to the account."""
    from fastapi import HTTPException
    code = str(persona.get("typeId") or "").lower()
    palette = context.get("palette")
    if code not in PERSONAS or (palette is not None and palette not in PALETTES):
        raise HTTPException(422, "请选择有效的人格和色板")
    result = {**profile, "persona_id": code, "palette": palette,
              "palette_source": "test_override" if palette else "persona_template_fallback",
              "axes": {}, "excluded_categories": [], "preferred_categories": [], "scene": None,
              "template_colors": persona.get("colors") or {}, "preview": True}
    result["version"] = digest(result)
    return result


def event_age_days(event, now):
    try:
        stamp = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        seconds = now.timestamp() - stamp.timestamp()
        return seconds / 86400 if seconds >= 0 else None
    except (ValueError, KeyError, TypeError):
        return None

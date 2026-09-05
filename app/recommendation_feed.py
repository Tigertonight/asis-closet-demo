"""Internal evidence-gated home feed. Pure scoring plus account-owned snapshots."""
from __future__ import annotations

import colorsys
import copy
import json
import math
import os
import re
import secrets
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.recommendation_diversity import outfit_features
from app.recommendation_profile import PALETTES, digest, event_age_days
from app.storage import storage_context

VERSION = "personal_home_v3.2"
WEIGHTS = {"color": .4, "persona": .3, "axes": .15, "scene": .1, "behavior": .05}
LOCK = threading.RLock()
SEASONS = {"春": "spring", "春季": "spring", "spring": "spring", "夏": "summer", "夏季": "summer", "summer": "summer", "秋": "autumn", "秋季": "autumn", "fall": "autumn", "autumn": "autumn", "冬": "winter", "冬季": "winter", "winter": "winter"}
SCENES = {"通勤": "commute", "上班": "commute", "commute": "commute", "日常": "daily", "休闲": "daily", "daily": "daily", "约会社交": "social", "社交": "social", "约会": "social", "social": "social", "正式活动": "formal", "正式": "formal", "formal": "formal", "旅行": "travel", "travel": "travel", "创意表达": "creative", "creative": "creative"}
MAIN = {"top", "outer", "bottom", "skirt", "dress"}


def normalize(values, vocabulary):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    result = set()
    for value in values or []:
        text = str(value).strip().lower()
        if text in {"四季", "all-season", "all_seasons"} and vocabulary is SEASONS:
            result.update(SEASONS.values())
        elif text in vocabulary:
            result.add(vocabulary[text])
    return result


def clamp(value):
    return min(1., max(0., float(value)))


def palette_affinity(hex_color, palette):
    """Continuous interpretable palette affinities; neutral support is not a hit."""
    try:
        if not isinstance(hex_color, str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", hex_color):
            return None
        rgb = tuple(int(hex_color.lstrip("#")[i:i+2], 16)/255 for i in (0, 2, 4))
        h, s, v = colorsys.rgb_to_hsv(*rgb)
    except (ValueError, TypeError, AttributeError):
        return None
    h *= 360
    distance = lambda center: min(abs(h-center), 360-abs(h-center))
    cool = max(math.exp(-(distance(center)/35)**2) for center in (190, 220, 250))
    earth = max(math.exp(-(distance(center)/30)**2) for center in (30, 55, 80))
    return clamp({
        "mono": (1-s)**2,
        "earth": earth*(.35+.65*s)*(1-max(0,v-.85)),
        "ocean": cool*(.25+.75*s),
        # Jewel tones are saturated and often deliberately deep.  Keep them
        # distinct from bright (which still requires high value) instead of
        # rejecting burgundy, amethyst and forest green for low lightness.
        "jewel": s*(.7 + .3*(1-abs(v-.5))),
        "bright": s*v,
        "pastel": v*(1-abs(s-.25)) if v >= .65 else v*.25,
    }[palette])


def color_score(outfit, profile):
    palette = profile.get("palette")
    main = [i for i in outfit.get("items", []) if (i.get("slot") or i.get("category")) in MAIN]
    weighted = []
    for item in main:
        swatches = (item.get("color_evidence") or {}).get("swatches") or []
        samples = []
        for swatch in swatches:
            if palette in PALETTES:
                score = palette_affinity(swatch.get("hex"), palette)
            else:
                # Template fallback is explicitly labelled and never a personal preference.
                colors = profile.get("template_colors") or {}
                targets = [c.get("value") for c in colors.get("items", [])] if isinstance(colors, dict) else []
                try:
                    rgb = [int(swatch["hex"].lstrip("#")[k:k+2], 16) for k in (0,2,4)]
                    distances = [math.sqrt(sum((rgb[j]-int(t.lstrip("#")[j*2:j*2+2],16))**2 for j in range(3))) for t in targets if isinstance(t,str) and len(t)==7]
                    score = max(0,1-min(distances)/300) if distances else None
                except (KeyError, ValueError):
                    score = None
            if score is not None:
                samples.append((score, max(0,float(swatch.get("weight") or 0))))
        total = sum(w for _,w in samples)
        if total:
            # Visual area estimate comes from reviewed garment observations, never accessory pixels.
            area = (item.get("visual") or {}).get("relative_area")
            area = float(area) if isinstance(area,(int,float)) and 0 < area <= 1 else (2 if item.get("category")=="dress" else 1)
            # The chosen hero is the user's main visual garment.  Give that
            # evidence enough influence to survive neutral supporting layers;
            # shoes and bags remain excluded above and can never create a hit.
            if item.get("outfit_role") == "hero":
                area *= 4
            weighted.append((sum(s*w for s,w in samples)/total, area))
    return sum(s*w for s,w in weighted)/sum(w for _,w in weighted) if weighted else None


def behavior_score(outfit, events, now):
    relevant = []
    features = outfit_features(outfit)[2]
    for event in events:
        age = event_age_days(event, now)
        if age is None or age > 30 or event.get("event_type") == "impression":
            continue
        exact = event.get("entity_id") == outfit["outfit_id"]
        related = set((event.get("context") or {}).get("style_family_ids") or []) & features
        if not exact and not related:
            continue
        amount = {"like": .3, "favorite": .45, "tryon": .25, "save": .35, "worn": .2, "dislike": -.5}.get(event.get("event_type"),0)
        relevant.append(amount * 2**(-age/7) * (1 if exact else .25))
    return clamp(.5 + max(-.5,min(.5,sum(relevant)))) if relevant else None


def rank_candidates(catalog, profile, context, events=(), now=None):
    now = now or datetime.now(timezone.utc)
    season = normalize(context.get("season_tags"), SEASONS)
    scene = normalize(context.get("scene_tags") or profile.get("scene") or "daily", SCENES)
    excluded = set(profile.get("excluded_categories") or [])
    only = set(context.get("categories") or profile.get("preferred_categories") or [])
    ranked, held = [], Counter()
    for outfit in catalog:
        v = outfit.get("visual") or {}
        items = outfit.get("items") or []
        categories = {i.get("category") for i in items}
        outfit_seasons = normalize(v.get("seasons"), SEASONS)
        outfit_scenes = normalize(v.get("scenes"), SCENES)
        reason = None
        if v.get("conflicts") or not items or not outfit.get("tryon_ready"):
            reason = "structure_or_asset"
        elif v.get("expression") == "experimental" and (
                not scene or "daily" in scene or not outfit_scenes or not scene & outfit_scenes):
            # A valid creative review is not approval for daily or light exploration.
            reason = "experimental_requires_confirmed_nondaily_scene"
        elif categories & excluded or (only and not categories & only):
            reason = "category_preference"
        elif any(i.get("laundry_status") in {"laundry","unavailable"} for i in items):
            reason = "unavailable"
        elif season and outfit_seasons and not season & outfit_seasons:
            reason = "season"
        elif scene and outfit_scenes and not scene & outfit_scenes:
            reason = "scene"
        ps = (v.get("persona_scores") or {}).get(profile.get("persona_id"))
        if not isinstance(ps,(int,float)) or isinstance(ps,bool) or not math.isfinite(ps) or not .55 <= ps <= 1:
            reason = reason or "persona_visual_insufficient"
        if reason:
            held[reason] += 1
            continue
        color = color_score(outfit, profile)
        # Different palette preferences must remain a real eligibility signal.
        if profile.get("palette") and (color is None or color < .3):
            held["color_preference"] += 1
            continue
        axes = [1-abs(float(value)-float(v["axes"][key]))/100 for key,value in profile.get("axes",{}).items() if isinstance((v.get("axes") or {}).get(key),(int,float))]
        parts = {"color": color, "persona": clamp(ps), "axes": sum(axes)/len(axes) if axes else None,
                 "scene": 1. if scene and outfit_scenes and scene & outfit_scenes else None,
                 "behavior": behavior_score(outfit, events, now)}
        weights = dict(WEIGHTS)
        try:
            overrides = json.loads(os.getenv("SELFIT_RECOMMENDATION_V3_WEIGHTS", "{}"))
            if set(overrides)==set(weights) and all(isinstance(n,(int,float)) and 0<n<=1 for n in overrides.values()): weights=overrides
        except (ValueError,TypeError): pass
        denominator = sum(weights[k] for k,value in parts.items() if value is not None)
        contributions = {k: weights[k]*value/denominator for k,value in parts.items() if value is not None}
        top = max(contributions, key=contributions.get)
        evidence = str(outfit.get("visual_evidence") or "").strip()[:80]
        labels = {"color": f"你偏好的{PALETTES.get(profile.get('palette'),'配色')}" if profile.get("palette") else "参考风格报告的推荐配色",
                  "persona": evidence or "参考这套搭配的风格特征", "axes": "呼应你选择的审美倾向", "scene": "适合你这次选择的场景" if context.get("scene_tags") or profile.get("scene") else "适合日常穿着",
                  "behavior": "参考你近期喜欢的穿搭"}
        exposure = sum(2**(-age/2) for event in events if event.get("entity_id")==outfit["outfit_id"] and event.get("event_type")=="impression"
                       and (age:=event_age_days(event,now)) is not None and age<=7)
        ranked.append({**outfit, "recommendation": {"score": round(100*sum(contributions.values())-min(8,exposure),4),
                       "components": parts, "contributions": contributions, "primary_reason": labels[top],
                       "reasons": [labels[k] for k in sorted(contributions,key=contributions.get,reverse=True)],
                       "algorithm": VERSION, "evidence_status": "ai_validation_not_human_review"}})
    ranked.sort(key=lambda o:(-o["recommendation"]["score"], o["outfit_id"]))
    return ranked, dict(held)


def structure(outfit):
    return (outfit.get("visual") or {}).get("structure")


def select_sequence(ranked, limit=100, recent_hero=(), category_filtered=False, expression_roles=None):
    """Strict expression slots; short feeds report shortages, never use filler."""
    candidates = list(ranked)
    selected, first_counts = [], Counter()
    features = {o["outfit_id"]:outfit_features(o) for o in ranked}
    roles = list(expression_roles or ["easy","easy","easy","typical","easy","easy","easy","easy","typical","explore"])
    if len(roles) != 10 or any(role not in {"easy", "typical", "explore"} for role in roles):
        raise ValueError("The first-page expression sequence must contain exactly 10 supported roles")
    gaps = []
    for position in range(limit):
        history = [features[o["outfit_id"]] for o in selected]
        parents = {f[0] for f in history[-7:]}
        main = Counter(g for f in history[-9:] for g in f[1])
        families = Counter(g for f in history[-9:] for g in f[2])
        eligible = [o for o in candidates if features[o["outfit_id"]][0] not in parents
                    and all(main[g]<2 for g in features[o["outfit_id"]][1])
                    and all(families[g]<2 for g in features[o["outfit_id"]][2])]
        if position < 10:
            role = roles[position]
            eligible = [o for o in eligible if o["visual"].get("expression")==role]
            if not category_filtered:
                eligible = [o for o in eligible if structure(o) in {"pants","skirt","dress"} and first_counts[structure(o)] < 5]
                missing = {"pants","skirt","dress"} - first_counts.keys()
                if 10-position <= len(missing):
                    eligible = [o for o in eligible if structure(o) in missing]
            if position < 4:
                unseen = [o for o in eligible if o["outfit_id"] not in recent_hero]
                if unseen: eligible = unseen
        if not eligible:
            gaps.append({"position": position, "reason": "quality_expression_or_diversity_supply", "required_expression": roles[position] if position<10 else None})
            break
        pick = eligible[0]
        selected.append(pick)
        candidates.remove(pick)
        if position < 10: first_counts[structure(pick)]+=1
    return selected, gaps


def _directory():
    return storage_context().user_root / "recommendation_sessions"


def _read_snapshot(token):
    if not isinstance(token,str) or not re.fullmatch(r"[a-f0-9]{32}",token):
        raise HTTPException(422,"推荐会话无效")
    path = _directory() / f"{token}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError,ValueError):
        raise HTTPException(410,"这轮推荐已过期，请换一批")
    if data.get("user_id") != storage_context().user_id:
        raise HTTPException(404,"没有找到这轮推荐")
    if datetime.now(timezone.utc).timestamp()-data["created_at"] > 86400:
        raise HTTPException(410,"这轮推荐已过期，请换一批")
    return data


def _write_snapshot(data):
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{data['session_id']}.json"
    temporary = directory / f"{data['session_id']}.{secrets.token_hex(4)}.tmp"
    temporary.write_text(json.dumps(data,ensure_ascii=False))
    temporary.replace(path)


def _page(data, start, first=False):
    rows = data["rows"]
    end = min(len(rows),10 if first else start+6)
    suppressed = set(data.get("suppressed_outfit_ids") or [])
    carousel = [row for row in rows[:min(4,len(rows))] if row["outfit_id"] not in suppressed] if first else []
    page_rows = rows[4:end] if first else rows[start:end]
    feed = [row for row in page_rows if row["outfit_id"] not in suppressed]
    next_cursor = f"{end}:{digest([data['session_id'],end,data['profile_version']])[:24]}" if end<len(rows) else None
    return {"algorithm":data.get("strategy_version",VERSION), "session_id":data["session_id"], "profile_version":data["profile_version"],
            "content_version":data["content_version"], "next_cursor":next_cursor, "has_more":bool(next_cursor),
            "outfits":feed, "carousel":carousel, "total":len(rows), "offset":start, "next_offset":0,
            "validation":True, "supply_gaps":data["gaps"], "selection":data.get("selection"),
            "validation_bundle":data.get("validation_bundle"),
            "diversity":{"stop_reason":None if next_cursor else "diversity_limit" if data["gaps"] else "pool_exhausted"}}


def create_feed(profile, catalog, context, events=(), content_version="unknown", validation_bundle=None,
                expression_roles=None):
    now = datetime.now(timezone.utc)
    ranked, rejected = rank_candidates(catalog,profile,context,events,now)
    recent = {e.get("entity_id") for e in events if e.get("event_type")=="impression" and (age:=event_age_days(e,now)) is not None and age<1}
    selection = None
    if validation_bundle:
        from app.recommendation_sequence import daily_candidates, select_flexible_sequence
        ranked, daily_rejected = daily_candidates(ranked, winter="winter" in normalize(context.get("season_tags"), SEASONS))
        rejected.update(daily_rejected)
        rows,gaps,selection = select_flexible_sequence(ranked, recent_hero=recent, category_filtered=bool(context.get("categories") or profile.get("preferred_categories")))
    else:
        rows,gaps = select_sequence(ranked, recent_hero=recent,
                                    category_filtered=bool(context.get("categories") or profile.get("preferred_categories")),
                                    expression_roles=expression_roles)
    data = {"session_id":secrets.token_hex(16), "user_id":storage_context().user_id,
            "created_at":now.timestamp(), "profile_version":profile["version"], "content_version":content_version,
            "context":copy.deepcopy(context),
            "preview":bool(profile.get("preview")), "rows":rows, "gaps":gaps,
            "rejected":rejected, "feedback_ids":[], "validation_bundle":validation_bundle,
            "strategy_version":(validation_bundle or {}).get("strategy", VERSION), "selection":selection}
    with LOCK: _write_snapshot(data)
    return _page(data,0,True)


def continue_feed(token, cursor, profile):
    with LOCK:
        data = _read_snapshot(token)
        if data["profile_version"] != profile["version"]:
            raise HTTPException(409,"偏好已更新，请重新加载推荐")
        try:
            value,signature = str(cursor).split(":")
            start = int(value)
        except (ValueError,TypeError):
            raise HTTPException(422,"分页信息无效")
        if start<10 or start>len(data["rows"]) or (start-10)%6 or signature!=digest([token,start,data["profile_version"]])[:24]:
            raise HTTPException(422,"分页信息无效")
        return _page(data,start)


def validate_feedback(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("context", {}), dict):
        raise HTTPException(422, "反馈格式无效")
    context = payload.get("context") or {}
    token = context.get("recommendation_session")
    if not token:
        return payload  # backward-compatible non-feed feedback
    with LOCK:
        data = _read_snapshot(token)
        if data.get("preview"):
            raise HTTPException(409,"测试模式不记录正式偏好")
        outfit = next((o for o in data["rows"] if o["outfit_id"]==payload.get("entity_id")),None)
        if outfit is None:
            raise HTTPException(422,"反馈不属于这轮推荐")
        if payload.get("event_type")=="impression":
            ratio, duration = context.get("visible_ratio"), context.get("visible_ms")
            if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (ratio, duration))
                    or not .5 <= ratio <= 1 or duration < 1000):
                raise HTTPException(422,"曝光时长不足或无效")
        if payload.get("event_type") == "dislike":
            _, disliked_main, disliked_families = outfit_features(outfit)
            target_index = next(index for index, row in enumerate(data["rows"]) if row["outfit_id"] == outfit["outfit_id"])
            suppressed = set(data.get("suppressed_outfit_ids") or [])
            for row in data["rows"][target_index + 1:]:
                _, main_ids, families = outfit_features(row)
                if disliked_main & main_ids or disliked_families & families:
                    suppressed.add(row["outfit_id"])
            data["suppressed_outfit_ids"] = sorted(suppressed)
            _write_snapshot(data)
        return {**payload,"context":{**context,"style_family_ids":sorted(outfit_features(outfit)[2]),"strategy_version":data.get("strategy_version",VERSION)}}

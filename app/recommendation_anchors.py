"""Strict P0 anchor admission.

The manifest is a release allow-list, not a content generator.  Missing,
stale, self-reviewed, or partially reviewed evidence always yields an empty
pool so inventory pressure can never lower the publication bar.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.selfit_content_quality import record_fingerprint, review_is_current
from app.recommendation_diversity import FAMILY_PATH, main_recipe_signature

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "app/data/selfit-p0-anchors.v1.json"
DEFAULT_BLIND_RESULT = ROOT / "app/data/selfit-p0-blind-review.v1.json"
PERSONAS = frozenset({
    "mute", "iced", "heir", "ease", "melt", "wabi", "flou", "neon",
    "edge", "bolt", "film", "jade", "loop", "noir", "void", "oops",
})
TARGET_EXPRESSIONS = Counter({"easy": 4, "typical": 4, "explore": 2})
P0_SEQUENCE_ROLES = (
    "easy", "easy", "typical", "easy", "typical",
    "easy", "explore", "typical", "typical", "explore",
)
MAIN_STRUCTURES = frozenset({"pants", "skirt", "dress"})
INTERNAL_COPY = re.compile(
    r"\b(?:MUTE|ICED|HEIR|EASE|MELT|WABI|FLOU|NEON|EDGE|BOLT|FILM|JADE|LOOP|NOIR|VOID|OOPS)\b"
    r"|\b(?:provider|pipeline|confidence|json|mask)\b",
    re.IGNORECASE,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def _read_json(path: str, stamp: int) -> dict[str, Any]:
    del stamp
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def load_json(path: Path) -> dict[str, Any]:
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        stamp = 0
    return _read_json(str(path), stamp)


def configured_paths() -> tuple[Path, Path]:
    return (
        Path(os.getenv("SELFIT_P0_ANCHOR_MANIFEST", str(DEFAULT_MANIFEST))),
        Path(os.getenv("SELFIT_P0_BLIND_REVIEW", str(DEFAULT_BLIND_RESULT))),
    )


def adapt_released_anchor(row: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Apply only classifications backed by a fully validated release."""
    persona = str(entry["persona"]).lower()
    visual = dict(row.get("visual") or {})
    visual["persona_scores"] = {**(visual.get("persona_scores") or {}), persona: 1.0}
    visual["scenes"] = sorted(set(visual.get("scenes") or []) | {"daily"})
    return {**row, "title": entry["user_title"], "visual": visual,
            "anchor_release_persona": persona}


def enabled() -> bool:
    return os.getenv("SELFIT_P0_ANCHORS_ENABLED", "0").strip().lower() in {"1", "true", "yes"}


def blind_review_errors(result: dict[str, Any], package_id: str,
                        anchors: list[dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict) or not result:
        return ["blind review result is missing"]
    if not package_id or result.get("package_id") != package_id:
        errors.append("blind review package does not match anchor manifest")
    if result.get("identity_verification") != "declaration_only" or not str(result.get("reviewer") or "").strip():
        errors.append("independent reviewer declaration is missing")
    if result.get("independent") is not True or result.get("labels_hidden") is not True:
        errors.append("independent and blinded declarations must be true")
    if result.get("samples") != 160:
        errors.append("blind review must contain 160 unique samples")
    def ratio(value):
        return float(value) if (type(value) in (int, float) and math.isfinite(value)
                                and 0 <= value <= 1) else -1.0

    if ratio(result.get("top1_accuracy")) < .70:
        errors.append("overall blind Top-1 is below 70%")
    if ratio(result.get("top2_accuracy")) < .90:
        errors.append("overall blind Top-2 is below 90%")
    by_persona = result.get("by_persona") if isinstance(result.get("by_persona"), dict) else {}
    for persona in sorted(PERSONAS):
        row = by_persona.get(persona) if isinstance(by_persona.get(persona), dict) else {}
        samples = row.get("samples") if type(row.get("samples")) is int else 0
        hits1, hits2 = row.get("top1_hits"), row.get("top2_hits")
        valid_hits = (type(hits1) is int and type(hits2) is int
                      and 0 <= hits1 <= hits2 <= samples)
        if not valid_hits:
            errors.append(f"{persona}: invalid blind hit counts")
        top1 = hits1 / samples if valid_hits and samples > 0 else 0
        top2 = hits2 / samples if valid_hits and samples > 0 else 0
        if samples != 10:
            errors.append(f"{persona}: blind review sample count must be 10")
        if top1 < .60:
            errors.append(f"{persona}: blind Top-1 is below 60%")
        if top2 < .80:
            errors.append(f"{persona}: blind Top-2 is below 80%")
    decisions = result.get("decisions") if isinstance(result.get("decisions"), list) else []
    if len(decisions) != 160:
        errors.append("blind review decisions must contain 160 rows")
    elif any(not isinstance(row, dict) or row.get("verdict") != "accept" for row in decisions):
        errors.append("blind review contains reject or unresolved uncertain decisions")
    measured = defaultdict(Counter)
    seen_tokens, seen_ids = set(), set()
    anchor_by_id = {row.get("outfit_id"): row for row in anchors or []}
    for row in decisions:
        if not isinstance(row, dict):
            errors.append("blind decision must be an object")
            continue
        token, oid = row.get("token"), row.get("outfit_id")
        if (not isinstance(token, str) or not token or not isinstance(oid, str) or not oid):
            errors.append("blind decision token and outfit_id must be nonempty strings")
            continue
        if token in seen_tokens or oid in seen_ids:
            errors.append("blind review contains duplicate sample tokens or outfit IDs")
        seen_tokens.add(token); seen_ids.add(oid)
        persona, top1, top2 = row.get("expected_persona"), row.get("top1"), row.get("top2")
        if (not all(isinstance(value, str) and value in PERSONAS for value in (persona, top1, top2))
                or top1 == top2 or not isinstance(row.get("reason"), str) or not row["reason"].strip()
                or not isinstance(row.get("issues"), list)):
            errors.append(f"{token}: incomplete blind decision")
            continue
        if anchors is not None:
            anchor = anchor_by_id.get(oid)
            if (not anchor or anchor.get("persona") != persona
                    or anchor.get("record_fingerprint") != row.get("record_fingerprint")):
                errors.append(f"{token}: blind decision is stale or mismatched to anchor")
        measured[persona]["samples"] += 1
        measured[persona]["top1_hits"] += top1 == persona
        measured[persona]["top2_hits"] += persona in (top1, top2)
    if anchors is not None and seen_ids != set(anchor_by_id):
        errors.append("blind decisions must cover the exact current anchors")
    for persona in PERSONAS:
        declared = by_persona.get(persona) or {}
        if not isinstance(declared, dict) or any(
            declared.get(field) != measured[persona][field]
            for field in ("samples", "top1_hits", "top2_hits")
        ):
            errors.append(f"{persona}: blind summary does not match individual decisions")
    total = sum(measured.values(), Counter())
    for name in ("top1", "top2"):
        actual = total[name + "_hits"] / total["samples"] if total["samples"] else -1
        if not math.isclose(ratio(result.get(name + "_accuracy")), actual, abs_tol=1e-9):
            errors.append(f"overall blind {name} summary does not match individual decisions")
    return errors


def validate_manifest(
    manifest: dict[str, Any],
    catalog: list[dict[str, Any]],
    raw_outfits: list[dict[str, Any]],
    *,
    content_version: str,
    visual_version: str,
    family_registry_sha256: str,
    blind_result: dict[str, Any] | None = None,
    require_release: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("anchor manifest schema_version must be 1")
    if require_release and manifest.get("status") != "approved":
        errors.append("anchor manifest is not approved")
    if manifest.get("content_version") != content_version:
        errors.append("anchor manifest content version is stale")
    if manifest.get("visual_version") != visual_version:
        errors.append("anchor manifest visual version is stale")
    if manifest.get("family_registry_sha256") != family_registry_sha256:
        errors.append("anchor manifest style-family registry is stale")
    anchors = manifest.get("anchors") if isinstance(manifest.get("anchors"), list) else []
    if len(anchors) != 160:
        errors.append("anchor manifest must contain exactly 160 rows")
    ids = [str(row.get("outfit_id") or "") for row in anchors if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        errors.append("anchor outfit IDs must be unique")

    catalog_by_id = {str(row.get("outfit_id") or ""): row for row in catalog}
    raw_by_id = {str(row.get("id") or ""): row for row in raw_outfits}
    personas: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    parents: list[str] = []
    clothing_recipes: dict[tuple[str, ...], str] = {}
    for entry in anchors:
        if not isinstance(entry, dict):
            errors.append("anchor row must be an object")
            continue
        oid = str(entry.get("outfit_id") or "")
        adapted, raw = catalog_by_id.get(oid), raw_by_id.get(oid)
        if not adapted or not raw:
            errors.append(f"{oid or '<missing>'}: anchor is absent from the current eligible catalog")
            continue
        if entry.get("record_fingerprint") != record_fingerprint(raw):
            errors.append(f"{oid}: anchor record fingerprint is stale")
        if require_release and not review_is_current(raw):
            errors.append(f"{oid}: current four-gate review is missing")
        persona = str(raw.get("primary_persona") or "").lower()
        if persona not in PERSONAS:
            errors.append(f"{oid}: invalid primary persona")
            continue
        if str(entry.get("persona") or "").lower() != persona:
            errors.append(f"{oid}: manifest persona does not match content")
        visual = adapted.get("visual") if isinstance(adapted.get("visual"), dict) else {}
        expression = str(entry.get("expression") or visual.get("expression") or "")
        structure = str(entry.get("structure") or visual.get("structure") or "")
        if expression != visual.get("expression") or structure != visual.get("structure"):
            errors.append(f"{oid}: manifest classifications do not match visual evidence")
        if expression not in TARGET_EXPRESSIONS:
            errors.append(f"{oid}: expression must be easy, typical, or explore")
        if structure not in MAIN_STRUCTURES:
            errors.append(f"{oid}: invalid main structure")
        user_title = str(entry.get("user_title") or "").strip()
        if not user_title:
            errors.append(f"{oid}: user title is missing")
        elif INTERNAL_COPY.search(user_title):
            errors.append(f"{oid}: user title exposes an internal code")
        roles = raw.get("slot_roles") if isinstance(raw.get("slot_roles"), dict) else {}
        if sum(role == "hero" for role in roles.values()) != 1:
            errors.append(f"{oid}: outfit must have exactly one visual hero")
        if int(visual.get("layering") or 1) > 1 and not raw.get("layer_graph"):
            errors.append(f"{oid}: layered outfit is missing layer_graph")
        parent = str(adapted.get("parent_outfit_id") or oid)
        parents.append(parent)
        signature = main_recipe_signature(adapted)
        if not signature:
            errors.append(f"{oid}: anchor has no main garments")
        elif signature in clothing_recipes:
            errors.append(f"{oid}: same main-garment recipe as {clothing_recipes[signature]}; accessory changes are not distinct parents")
        else:
            clothing_recipes[signature] = oid
        personas[persona].append((entry, adapted, raw))

    if len(parents) != len(set(parents)):
        errors.append("all 160 anchors must use distinct parent recipes")
    for persona in sorted(PERSONAS):
        rows = personas.get(persona, [])
        if len(rows) != 10:
            errors.append(f"{persona}: anchor count must be 10")
            continue
        expressions = Counter(str(entry.get("expression")) for entry, _, _ in rows)
        if expressions != TARGET_EXPRESSIONS:
            errors.append(f"{persona}: expression mix must be 4 easy / 4 typical / 2 explore")
        structures = Counter(str(entry.get("structure")) for entry, _, _ in rows)
        if set(structures) != MAIN_STRUCTURES or max(structures.values(), default=0) > 5:
            errors.append(f"{persona}: pants/skirt/dress must all appear and each stay at or below 5")
        main_ids, families = Counter(), Counter()
        for _, adapted, _ in rows:
            for item in adapted.get("items") or []:
                if (item.get("slot") or item.get("category")) in {"top", "outer", "bottom", "skirt", "dress"}:
                    main_ids[str(item.get("item_id"))] += 1
                    families[str(item.get("style_family_id") or "item:" + str(item.get("item_id")))] += 1
        if max(main_ids.values(), default=0) > 2:
            errors.append(f"{persona}: a main garment appears more than twice")
        if max(families.values(), default=0) > 2:
            errors.append(f"{persona}: a style family appears more than twice")

    package_id = str(manifest.get("blind_review_package_id") or "")
    if require_release:
        errors.extend(blind_review_errors(blind_result or {}, package_id, anchors))
    return {
        "valid": not errors,
        "errors": errors,
        "anchors": anchors,
        "counts": {persona: len(personas.get(persona, [])) for persona in sorted(PERSONAS)},
    }


def approved_anchor_pool(
    catalog: list[dict[str, Any]],
    raw_outfits: list[dict[str, Any]],
    *,
    content_version: str,
    visual_version: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path, blind_path = configured_paths()
    manifest, blind = load_json(manifest_path), load_json(blind_path)
    result = validate_manifest(
        manifest,
        catalog,
        raw_outfits,
        content_version=content_version,
        visual_version=visual_version,
        family_registry_sha256=_sha256(FAMILY_PATH) if FAMILY_PATH.is_file() else "missing",
        blind_result=blind,
        require_release=True,
    )
    result["manifest_path"] = str(manifest_path)
    result["manifest_sha256"] = _sha256(manifest_path) if manifest_path.is_file() else None
    result["blind_result_path"] = str(blind_path)
    result["blind_result_sha256"] = _sha256(blind_path) if blind_path.is_file() else None
    if not result["valid"]:
        return [], result
    entries = {str(row["outfit_id"]): row for row in result["anchors"]}
    released = []
    for row in catalog:
        entry = entries.get(str(row.get("outfit_id")))
        if not entry:
            continue
        # The release's four-gate persona decision and independent blind review
        # supersede the earlier AI-candidate score. Runtime may consume that
        # approved classification only after validate_manifest has passed.
        released.append(adapt_released_anchor(row, entry))
    return released, result

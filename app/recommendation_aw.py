"""Opt-in autumn/winter validation bundle. Never mutates the production pool."""
import json
import os
from copy import deepcopy
from pathlib import Path

from app.recommendation_diversity import style_family_map
from app.recommendation_profile import digest, validation_enabled
from app.recommendation_sequence import VERSION
from app.recommendation_visual import asset_sha, valid_observation
from app.selfit_content_quality import record_fingerprint

DEFAULT_FAMILIES = Path(__file__).resolve().parents[1] / "docs/audits/20260903-personal-home-visual/family-review/garment-style-families.native-draft.json"
DEFAULT_RECOMPOSITIONS = Path(__file__).resolve().parents[1] / "docs/audits/20260904-aw-supply/recompose.batch01.rendered.json"
DEFAULT_RECOMPOSITION_REVIEW = Path(__file__).resolve().parents[1] / "docs/audits/20260904-aw-supply/recompose.batch01.native-review.json"
DEFAULT_RECOMPOSITION_INDEX = Path(__file__).resolve().parents[1] / "docs/audits/20260904-aw-supply/recomposition-index.json"


def enabled(user_id):
    return validation_enabled(user_id) and os.getenv("SELFIT_RECOMMENDATION_AW_ENABLED", "0").lower() in {"1", "true"}


def validation_context(context, profile):
    """Scope this experiment to explicit autumn/winter daily conditions.

    An operator may configure a validation season; it is not inferred weather.
    Unsupported or unknown explicit selections must not silently become autumn.
    """
    from app.recommendation_feed import normalize, SEASONS, SCENES
    result = deepcopy(context)
    if not result.get("season_tags"):
        configured = os.getenv("SELFIT_RECOMMENDATION_AW_SEASON", "")
        if configured:
            result["season_tags"] = [configured]
            result["season_source"] = "internal_validation_configuration"
    seasons = normalize(result.get("season_tags"), SEASONS)
    scenes = normalize(result.get("scene_tags") or profile.get("scene") or "daily", SCENES)
    if len(seasons) != 1 or not seasons <= {"autumn", "winter"} or scenes != {"daily"}:
        return None
    return result


def load_recomposition_candidates(garments, visual, rendered=None, review=None, garment_manifest=None):
    """Load separately reviewed draft recipes for the internal AW experiment.

    This adapter never changes the published pool and never admits needs-review
    entries. Every cover and record remains fingerprint-bound.
    """
    if rendered is None and review is None:
        custom_rendered = os.getenv("SELFIT_RECOMMENDATION_AW_RECOMPOSITIONS")
        custom_review = os.getenv("SELFIT_RECOMMENDATION_AW_RECOMPOSITION_REVIEW")
        if custom_rendered or custom_review:
            if not custom_rendered or not custom_review:
                raise ValueError("Both custom recomposition paths are required")
            return load_recomposition_candidates(garments, visual,
                json.loads(Path(custom_rendered).read_text()), json.loads(Path(custom_review).read_text()))
        index = json.loads(DEFAULT_RECOMPOSITION_INDEX.read_text())
        if index.get("schema_version") != 1 or not index.get("version") or not index.get("batches"):
            raise ValueError("Invalid recomposition index")
        rows = []
        root = DEFAULT_RECOMPOSITION_INDEX.parent
        for batch in index["batches"]:
            batch_rendered = json.loads((root / batch["rendered"]).read_text())
            batch_review = json.loads((root / batch["review"]).read_text())
            if ((batch_rendered.get("version") or batch_rendered.get("batch_id")) != batch["rendered_version"]
                    or batch_review.get("version") != batch["review_version"]):
                raise ValueError("Stale recomposition index")
            batch_garments, batch_visual = garments, visual
            manifest = None
            if batch.get("garment_manifest"):
                manifest = json.loads((root / batch["garment_manifest"]).read_text())
                if (manifest.get("version") != batch.get("garment_manifest_version")
                        or manifest.get("production_approved") is not False):
                    raise ValueError("Stale generated garment manifest")
                batch_garments = list(garments) + list(manifest.get("garments") or [])
                batch_visual = deepcopy(visual)
                batch_visual.setdefault("garments", {}).update(manifest.get("visual") or {})
            batch_rows, _ = load_recomposition_candidates(batch_garments, batch_visual, batch_rendered, batch_review, manifest)
            rows.extend(batch_rows)
        if len({r["outfit_id"] for r in rows}) != len(rows):
            raise ValueError("Duplicate recomposition ID")
        return rows, index["version"]
    if rendered is None or review is None:
        raise ValueError("Rendered and review must be supplied together")
    if garment_manifest is not None:
        manifest_ids = {row["id"] for row in garment_manifest.get("garments") or []}
        if len(manifest_ids) != len(garment_manifest.get("garments") or []):
            raise ValueError("Duplicate generated garment ID")
        for row in garment_manifest.get("garments") or []:
            observation = (garment_manifest.get("visual") or {}).get(row["id"])
            if not valid_observation(row, observation, row["assets"]["image_url"], "garments"):
                raise ValueError("Invalid generated garment evidence")
    rendered_version = rendered.get("version") or rendered.get("batch_id")
    if review.get("source_rendered_version") != rendered_version or not review.get("version"):
        raise ValueError("Stale recomposition review")
    by_review = {r["outfit_id"]: r for r in review.get("entries", [])}
    by_garment = {g["id"]: g for g in garments}
    accepted = []
    for entry in rendered.get("entries", []):
        raw = entry.get("new_record") or {}
        observation = by_review.get(raw.get("id"))
        if not observation or observation.get("status") != "ai_candidate":
            continue
        if entry.get("record_fingerprint") != record_fingerprint(raw):
            raise ValueError("Stale recomposition record")
        cover = (raw.get("assets") or {}).get("image_url")
        if not valid_observation(raw, observation, cover, "outfits"):
            raise ValueError("Invalid recomposition observation")
        items = []
        for gid in raw.get("garment_ids") or []:
            garment = by_garment.get(gid)
            garment_observation = visual.get("garments", {}).get(gid)
            image = ((garment or {}).get("assets") or {}).get("image_url")
            if not garment or not valid_observation(garment, garment_observation, image, "garments"):
                raise ValueError("Invalid recomposition garment")
            source_category = str(garment.get("category") or "accessory")
            category = "top" if source_category == "outer" else "accessory" if source_category in {"hat", "scarf", "accessory"} else source_category
            items.append({
                "item_id": gid, "style_family_id": "item:" + gid, "image_id": gid,
                "outfit_role": (raw.get("slot_roles") or {}).get(gid),
                "category": category, "category_label": source_category,
                "subcategory": str(garment.get("subcategory") or source_category),
                "slot": source_category if source_category in {"outer", "hat", "scarf"} else None,
                "title": str(garment.get("subcategory") or source_category),
                "assets": {"cutout_path": image, "preview_path": image},
                "attributes": {"colors": list((garment.get("color_evidence") or {}).get("palette_names") or []),
                               "color_hex": list((garment.get("color") or {}).get("palette") or []),
                               "style_tags": list(garment.get("details") or []),
                               "scene_tags": list(garment.get("scene_tags") or []),
                               "season_tags": list(garment.get("season_tags") or [])},
                "quality": {"status": "usable", "score": 1.0, "reasons": ["bound_visual_review"]},
                "source": {"type": "aw_reviewed_draft", "content_version": rendered_version},
                "tryon_ready": True, "favorite": False, "deleted": False,
                "visual": garment_observation["observations"], "color_evidence": garment.get("color_evidence") or {}
            })
        scores = observation["observations"].get("persona_scores") or {}
        reviewed_primary = max(scores, key=scores.get) if scores else str(raw.get("primary_persona") or "").lower()
        accepted.append({
            "outfit_id": raw["id"], "title": raw.get("title") or "秋季穿搭", "description": raw.get("description") or "",
            "item_ids": list(raw["garment_ids"]), "items": items, "scene_tags": list(raw.get("scene_tags") or []),
            "season_tags": list(raw.get("season_tags") or []), "primary_persona": reviewed_primary.upper(),
            "parent_outfit_id": raw.get("parent_outfit_id") or raw["id"], "recipe_kind": raw.get("kind"),
            "secondary_personas": list(raw.get("secondary_personas") or []), "cover_path": cover,
            "layout_snapshot_path": cover, "layout_version": (raw.get("assets") or {}).get("layout_version"),
            "layout_mode": "canonical_flatlay", "canvas": {"width": 1200, "height": 1500},
            "display_item_ids": list(raw["garment_ids"]), "overflow_items": [], "warnings": [],
            "source": "aw_reviewed_draft", "content_version": rendered_version, "curation": {},
            "favorite_count": 0, "favorite": False, "tryon_ready": True, "created_at": "", "updated_at": "", "deleted": False,
            "visual": observation["observations"], "visual_evidence": observation["evidence"],
            "visual_confidence": observation["confidence"]
        })
    if len(accepted) != sum(r.get("status") == "ai_candidate" for r in review.get("entries", [])):
        raise ValueError("Incomplete recomposition manifest")
    return accepted, review["version"]


def prepare_candidates(candidates, garments, visual, registry=None, supplemental_version=None):
    if registry is None:
        path = Path(os.getenv("SELFIT_RECOMMENDATION_AW_FAMILY_PATH", str(DEFAULT_FAMILIES)))
        registry = json.loads(path.read_text())
    if registry.get("visual_version") != visual.get("version") or not registry.get("version"):
        raise ValueError("Stale family review")
    mapping = style_family_map(garments, registry)
    expected = {g for f in registry.get("families", []) for g in f["members"]}
    if not expected or expected != mapping.keys():
        raise ValueError("Invalid family evidence")
    by_id = {g["id"]: g for g in garments}
    for family in registry["families"]:
        for gid in family["members"]:
            if (family.get("asset_sha256") or {}).get(gid) != asset_sha(by_id[gid]["assets"]["image_url"]):
                raise ValueError("Stale family asset")
    result = deepcopy(candidates)
    for row in result:
        for item in row["items"]:
            item["style_family_id"] = mapping.get(item["item_id"], "item:"+item["item_id"])
    versions = {"strategy":VERSION,"visual":visual["version"],"families":registry["version"],
                "supplemental": supplemental_version,
                "content":digest([(r["outfit_id"],r.get("cover_path"),[(i["item_id"],i["style_family_id"]) for i in r["items"]]) for r in result])}
    return result, versions

"""Design P0 shortage recipes from current, visually reviewed garment cutouts."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_diversity import style_family_map
from app.recommendation_visual import attach_visual, load_visual

MAIN = {"top", "outer", "bottom", "skirt", "dress"}
DECORATION_RANK = {"low": 0, "medium": 1, "high": 2}
TARGET_DECORATION = {"easy": 0, "typical": 1, "explore": 2}


def family(gid: str, families: dict[str, str]) -> str:
    return families.get(gid, "item:" + gid)


def eligible_main(
    gid: str,
    counts: Counter,
    family_counts: Counter,
    families: dict[str, str],
) -> bool:
    return counts[gid] < 2 and family_counts[family(gid, families)] < 2


def build(
    backlog_path: Path,
    anchor_path: Path,
    staging_path: Path,
    generated_garments_path: Path | None = None,
) -> dict:
    backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
    manifest = json.loads(anchor_path.read_text(encoding="utf-8"))
    staging = json.loads(staging_path.read_text(encoding="utf-8"))
    if backlog["source_anchor_manifest_sha256"] != __import__("hashlib").sha256(anchor_path.read_bytes()).hexdigest():
        raise ValueError("Backlog is not bound to the supplied anchor manifest")
    if manifest.get("staging_version") != staging.get("version"):
        raise ValueError("Staging is not bound to the supplied anchor manifest")

    pool, visual = closet.selfit_content_pool(), load_visual()
    garments = {row["id"]: row for row in pool.garments}
    generated_version = None
    if generated_garments_path:
        generated = json.loads(generated_garments_path.read_text(encoding="utf-8"))
        if generated.get("schema_version") != 1 or generated.get("production_approved") is not False:
            raise ValueError("Generated garment bundle must be an unpublished internal candidate")
        generated_version = generated.get("version")
        for row in generated.get("garments") or []:
            if row["id"] in garments:
                raise ValueError(f"Generated garment duplicates current pool: {row['id']}")
            garments[row["id"]] = row
        visual = {
            **visual,
            "garments": {**visual["garments"], **(generated.get("visual") or {})},
        }
    token_to_gid = {row["token"]: gid for gid, row in visual["garments"].items() if gid in garments}
    gid_to_token = {gid: token for token, gid in token_to_gid.items()}
    families = style_family_map(pool.garments)
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    catalog.extend(entry["catalog_record"] for entry in staging["entries"])
    by_id = {row["outfit_id"]: row for row in catalog}

    item_counts, family_counts = defaultdict(Counter), defaultdict(Counter)
    for anchor in manifest["anchors"]:
        persona = anchor["persona"]
        for item in by_id[anchor["outfit_id"]]["items"]:
            category = item.get("slot") or item.get("category")
            if category not in MAIN:
                continue
            gid = item["item_id"]
            item_counts[persona][gid] += 1
            family_counts[persona][family(gid, families)] += 1

    observations = {
        gid: row["observations"]
        for gid, row in visual["garments"].items()
        if gid in garments
    }
    accessories = {}
    for category in ("shoes", "bag"):
        accessories[category] = sorted(
            (
                gid for gid, obs in observations.items()
                if obs.get("category") == category and obs.get("decoration") == "low"
            ),
            key=lambda gid: gid_to_token[gid],
        )
        if not accessories[category]:
            raise ValueError(f"No low-decoration {category} available")

    accessory_index = Counter()
    recipes = []
    for task in backlog["tasks"]:
        persona, expression, structure = task["persona"], task["expression"], task["structure"]
        structure_category = "bottom" if structure == "pants" else structure
        allowed_hero_categories = {"dress"} if structure == "dress" else {"top", structure_category}
        target_rank = TARGET_DECORATION[expression]
        hero_candidates = [
            gid for gid, obs in observations.items()
            if obs.get("category") in allowed_hero_categories
            and persona in (obs.get("visual_personas") or [])
            and eligible_main(gid, item_counts[persona], family_counts[persona], families)
        ]
        if not hero_candidates:
            raise ValueError(f"{task['task_id']}: no persona hero remains within repetition caps")
        hero = min(hero_candidates, key=lambda gid: (
            abs(DECORATION_RANK.get(observations[gid].get("decoration"), 1) - target_rank),
            len(observations[gid].get("visual_personas") or []),
            item_counts[persona][gid],
            family_counts[persona][family(gid, families)],
            gid_to_token[gid],
        ))
        hero_category = observations[hero]["category"]
        main_ids = [hero]
        if structure != "dress":
            support_category = structure_category if hero_category == "top" else "top"
            support_candidates = [
                gid for gid, obs in observations.items()
                if obs.get("category") == support_category
                and obs.get("decoration") == "low"
                and gid != hero
                and eligible_main(gid, item_counts[persona], family_counts[persona], families)
            ]
            if not support_candidates:
                raise ValueError(f"{task['task_id']}: no neutral support remains within repetition caps")
            support = min(support_candidates, key=lambda gid: (
                item_counts[persona][gid],
                family_counts[persona][family(gid, families)],
                persona in (observations[gid].get("visual_personas") or []),
                gid_to_token[gid],
            ))
            main_ids.append(support)

        for gid in main_ids:
            item_counts[persona][gid] += 1
            family_counts[persona][family(gid, families)] += 1
        extra_ids = []
        for category in ("shoes", "bag"):
            rows = accessories[category]
            gid = rows[accessory_index[(persona, category)] % len(rows)]
            accessory_index[(persona, category)] += 1
            extra_ids.append(gid)
        item_ids = main_ids + extra_ids
        keywords = "、".join(task["persona_keywords"])
        recipes.append({
            "task_id": task["task_id"],
            "persona": persona.upper(),
            "palette": "evidence_first",
            "season": "autumn",
            "structure": structure,
            "hero": gid_to_token[hero],
            "items": [gid_to_token[gid] for gid in item_ids],
            "expression": expression,
            "intent": (
                f"{task['persona_name']} {expression} / {structure}："
                f"以“{keywords}”为人格证据，只保留一件主视觉，"
                "其余单品降低竞争并维持日常可穿。"
            ),
        })
    result = {
        "schema_version": 1,
        "batch_id": "p0-visual-gap-01",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "source_backlog": str(backlog_path),
        "source_anchor_manifest": str(anchor_path),
        "new_garments": [],
        "recipes": recipes,
    }
    if generated_garments_path:
        result["new_garment_manifest"] = str(
            generated_garments_path.resolve().relative_to(backlog_path.parent.resolve())
        )
        result["new_garment_version"] = generated_version
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backlog", type=Path, required=True)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--generated-garments", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite P0 recomposition evidence")
    result = build(args.backlog, args.anchor_manifest, args.staging, args.generated_garments)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"recipes": len(result["recipes"]), "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

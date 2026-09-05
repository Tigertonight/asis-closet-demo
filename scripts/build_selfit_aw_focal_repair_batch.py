"""Simplify accessory competition for focal-cohesion findings in bounded batches.

Only shoes and bags are replaced. Clothing conflicts are deliberately left for the
subsequent whole-outfit visual review to accept or reject.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

ACCESSORIES = {
    "dark": {
        "shoes": ["g0004", "g0254", "g0265"],
        "bag": ["g0005", "g0270", "g0513", "g0529"],
    },
    "earth": {
        "shoes": ["g0246", "g0250", "g0262", "g0267"],
        "bag": ["g0276", "g0278", "g0283", "g0593"],
    },
    "light": {
        "shoes": ["g0252", "g0261", "g0268", "g0501"],
        "bag": ["g0272", "g0273", "g0277", "g0285"],
    },
    "blue": {
        "shoes": ["g0248", "g0258", "g0264"],
        "bag": ["g0274", "g0275", "g0280", "g0290"],
    },
}


def palette(colors: set[str]) -> str:
    if colors & {"black", "charcoal", "gray"}:
        return "dark"
    if colors & {"brown", "taupe", "olive", "beige", "sage", "caramel"}:
        return "earth"
    if colors & {"navy", "ice_blue", "steel_blue", "cobalt", "denim_blue", "washed_blue"}:
        return "blue"
    return "light"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, choices=(5, 6), required=True)
    args = parser.parse_args()
    ledger = json.loads((AUDIT / "repair-ledger.initial.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    garments = visual["garments"]
    token_by_id = {gid: row["token"] for gid, row in garments.items()}

    eligible = []
    seen_parents = set()
    for row in ledger["entries"]:
        if row["primary_group"] != "focal_cohesion" or row["original_status"] != "needs_review":
            continue
        if row["source_parent_recipe"] in seen_parents:
            continue
        seen_parents.add(row["source_parent_recipe"])
        eligible.append(row)
    assert len(eligible) == 57
    selected = eligible[:48] if args.batch == 5 else eligible[48:]
    expected = 48 if args.batch == 5 else 9
    assert len(selected) == expected and len(selected) <= 48

    edits = []
    for position, row in enumerate(selected):
        clothing = []
        slots = {}
        for gid in row["source_garment_ids"]:
            observation = garments[gid]["observations"]
            category = observation["category"]
            if category in {"shoes", "bag"}:
                slots[category] = token_by_id[gid]
            else:
                clothing.extend(observation.get("main_colors") or [])
        assert set(slots) == {"shoes", "bag"}
        family = palette(set(clothing))
        replacement = {
            slots[category]: choices[position % len(choices)]
            for category, choices in ACCESSORIES[family].items()
        }
        edits.append({
            "token": row["token"],
            "replace": replacement,
            "intent": (
                f"保留原主服装，以低装饰 {family} 鞋包替换竞争性配件；"
                "仅降低配件噪音，主服装之间是否仍冲突必须重新看整套图。"
            ),
        })

    result = {
        "schema_version": 1,
        "batch_id": f"aw-repair-0{args.batch}",
        "source_visual_version": ledger["source_visual_version"],
        "status": "explicit_focal_accessory_edits_pending_native_review",
        "new_garments": [],
        "edits": edits,
    }
    target = AUDIT / f"repair-edits.batch0{args.batch}.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Focal repair batch changed; refusing to overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(target, len(edits))


if __name__ == "__main__":
    main()

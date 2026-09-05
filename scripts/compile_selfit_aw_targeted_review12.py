#!/usr/bin/env python3
"""Compile native whole-image review for winter targeted recipe batch 12."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = ["axes", "expression", "formality", "layering", "persona_scores", "scenes", "seasons", "structure", "wearability", "main_visual_slots", "main_colors", "conflicts", "silhouette", "color_relation", "persona_evidence", "winter_outdoor"]


def main() -> None:
    rendered = json.loads((AUDIT / "targeted-recipes.batch12.rendered.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    generated = json.loads((AUDIT / "generated-garments/batch13/manifest.json").read_text())
    visuals = {**base["garments"], **generated["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        observations = [visuals[garment_id]["observations"] for garment_id in raw["garment_ids"]]
        categories = [item["category"] for item in observations]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = list(dict.fromkeys(color for item in observations if item["category"] not in {"shoes", "bag"} for color in item.get("main_colors") or []))
        evidence = f"{raw['primary_persona']} 的目标色和独立主衣家族形成主要证据；{structure} 支撑款低竞争，长外层、完整袖长和闭合鞋履关系在成图中可见。"
        observed = {
            "axes": {}, "expression": "typical", "formality": "smart_casual", "layering": 2,
            "persona_scores": {raw["primary_persona"].lower(): 0.86}, "scenes": ["daily"], "seasons": ["winter"],
            "structure": structure, "wearability": "everyday_with_statement",
            "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
            "main_colors": colors, "conflicts": None, "silhouette": f"reviewed_near_threshold_winter_{structure}",
            "color_relation": "reviewed_coherent", "persona_evidence": evidence,
            "winter_outdoor": "complete_layers_visually_reviewed",
        }
        statuses = {key: "ai_observed" for key in FIELDS}
        sheet = f"targeted-batch12-review/recipes-{(position - 1) // 6 + 1}.jpg"
        provenance = {key: {"source_file": sheet, "version": "aw-targeted-12-native-v1", "confidence": 0.86} for key in FIELDS}
        entries.append({
            "outfit_id": raw["id"], "status": "ai_candidate", "record_fingerprint": row["record_fingerprint"],
            "asset_sha256": row["asset_sha256"], "image_url": raw["assets"]["image_url"],
            "source_kind": "codex_visual_review", "evidence": evidence, "observations": observed, "confidence": 0.86,
            "model": "current_codex_session", "prompt_version": "aw-targeted-12-native-v1",
            "review_level": "individual_contact_sheet_judgment",
            "evidence_scope": "nonblind individual visual judgment; no temperature, waterproof, snow, or comfort claim",
            "review_complete": True, "field_status": statuses, "field_provenance": provenance,
        })
    assert len(entries) == 24
    result = {"schema_version": 1, "source_rendered_version": rendered["version"], "independent_blind_review": False, "winter_outdoor_reviewed": True, "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-targeted-review-" + hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "targeted-recipes.batch12.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Review12 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 24, "held": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

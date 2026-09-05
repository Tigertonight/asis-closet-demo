"""Conservative non-blind preflight for P0 persona/context editorial review."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_visual import attach_visual, load_visual

DAILY = {"everyday", "everyday_with_statement"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite persona preflight evidence")
    manifest, staging = json.loads(args.anchor_manifest.read_text()), json.loads(args.staging.read_text())
    if manifest.get("staging_version") != staging.get("version"):
        raise ValueError("Staging version does not match anchor manifest")
    pool = closet.selfit_content_pool()
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, load_visual())
    catalog.extend(entry["catalog_record"] for entry in staging["entries"])
    by_id = {row["outfit_id"]: row for row in catalog}
    counts, rows = defaultdict(Counter), []
    for anchor in manifest["anchors"]:
        outfit = by_id[anchor["outfit_id"]]
        visual = outfit.get("visual") or {}
        persona = anchor["persona"]
        score = (visual.get("persona_scores") or {}).get(persona)
        score_pass = isinstance(score, (int, float)) and not isinstance(score, bool) and score >= .55
        scenes = set(visual.get("scenes") or [])
        context_pass = visual.get("wearability") in DAILY and (not scenes or "daily" in scenes)
        status = "candidate" if score_pass and context_pass else "needs_editorial_attention"
        counts[persona]["total"] += 1
        counts[persona]["persona_signal_pass"] += score_pass
        counts[persona]["daily_context_pass"] += context_pass
        counts[persona]["both_pass"] += score_pass and context_pass
        rows.append({
            "outfit_id": anchor["outfit_id"], "persona": persona,
            "expression": anchor["expression"], "structure": anchor["structure"],
            "observed_persona_score": score, "observed_scenes": sorted(scenes),
            "observed_wearability": visual.get("wearability"),
            "persona_signal_pass": score_pass, "daily_context_pass": context_pass,
            "status": status,
            "note": "AI preflight is triage only; it cannot pass or fail the four-gate editorial review.",
        })
    summary = {persona: dict(value) for persona, value in sorted(counts.items())}
    total_pass = sum(value["both_pass"] for value in counts.values())
    result = {
        "schema_version": 1, "status": "editorial_attention_required",
        "anchor_manifest_sha256": sha(args.anchor_manifest), "staging_sha256": sha(args.staging),
        "threshold": {"persona_score": .55, "wearability": sorted(DAILY), "scene": "daily_or_unspecified"},
        "summary": {"samples": len(rows), "preflight_both_pass": total_pass,
                    "preflight_attention": len(rows) - total_pass, "by_persona": summary},
        "rows": rows,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if total_pass == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())

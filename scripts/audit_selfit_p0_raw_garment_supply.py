#!/usr/bin/env python3
"""Audit immutable raw P0 garment inputs without editing image pixels."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = ROOT / "docs/audits/20260904-p0-acceptance/generated-garments"
PERSONAS = {"bolt", "edge", "neon", "noir", "oops", "void"}
TARGETS = {
    "bolt": Counter({"easy:pants": 1, "typical:skirt": 1, "explore:dress": 1, "explore:pants": 1}),
    "edge": Counter({"easy:pants": 1, "easy:skirt": 1, "typical:dress": 1, "explore:pants": 1}),
    "neon": Counter({"easy:pants": 1, "easy:skirt": 1, "easy:dress": 1, "typical:pants": 1,
                     "typical:skirt": 1, "explore:dress": 1, "explore:pants": 1}),
    "noir": Counter({"explore:dress": 1}),
    "oops": Counter({"easy:dress": 2}),
    "void": Counter({"easy:skirt": 2}),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(plan_path: Path) -> dict:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema_version") != 1 or not isinstance(plan.get("entries"), list):
        raise ValueError("invalid raw supply plan")
    tokens, slugs, sources = set(), set(), set()
    supplied = {persona: Counter() for persona in PERSONAS}
    rows, errors = [], []
    for entry in plan["entries"]:
        token, slug, persona = entry["token"], entry["slug"], entry["persona"]
        source = (AUDIT_ROOT / entry["source"]).resolve()
        if persona not in PERSONAS:
            errors.append(f"{token}: invalid persona {persona}")
        if token in tokens or slug in slugs or source in sources:
            errors.append(f"{token}: duplicate token, slug or source")
        tokens.add(token); slugs.add(slug); sources.add(source)
        if not source.is_relative_to(AUDIT_ROOT.resolve()) or not source.is_file():
            errors.append(f"{token}: missing or escaped source")
            continue
        with Image.open(source) as image:
            mode, size = image.mode, image.size
            if "A" not in image.getbands() and "transparency" not in image.info:
                errors.append(f"{token}: source has no alpha")
                rows.append({"token": token, "slug": slug, "persona": persona, "source": entry["source"],
                             "mode": mode, "size": list(size), "sha256": sha256(source),
                             "technical_status": "rejected_no_alpha"})
                continue
            alpha = image.convert("RGBA").getchannel("A")
            extrema = alpha.getextrema()
            meaningful = alpha.point(lambda value: 255 if value >= 8 else 0)
            bbox = meaningful.getbbox()
            if extrema != (0, 255) or not bbox:
                errors.append(f"{token}: invalid alpha range or empty subject")
                margins = None
            else:
                margins = {"left": bbox[0] / size[0], "top": bbox[1] / size[1],
                           "right": (size[0] - bbox[2]) / size[0],
                           "bottom": (size[1] - bbox[3]) / size[1]}
        for target in entry["targets"]:
            supplied[persona][target] += 1
        needs = size != (1200, 1200) or margins is None or min(margins.values()) < .10
        rows.append({"token": token, "slug": slug, "persona": persona, "source": entry["source"],
                     "targets": entry["targets"], "mode": mode, "size": list(size),
                     "sha256": sha256(source), "alpha_extrema": list(extrema),
                     "meaningful_bbox": list(bbox) if bbox else None,
                     "margins": {key: round(value, 4) for key, value in margins.items()} if margins else None,
                     "technical_status": "requires_authorized_normalization" if needs else "raw_technical_ready"})
    for persona, expected in TARGETS.items():
        if supplied[persona] != expected:
            errors.append(f"{persona}: target coverage {dict(supplied[persona])} != {dict(expected)}")
    displayed_plan = str(plan_path.relative_to(ROOT)) if plan_path.is_relative_to(ROOT) else str(plan_path)
    return {
        "schema_version": 1,
        "formal_acceptance": False,
        "scope": "raw garment supply only; no outfit, four-gate or blind-review approval",
        "plan": displayed_plan,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "status": "raw_supply_complete_pending_normalization" if not errors else "raw_supply_invalid",
        "summary": {"raw_garments": len(rows), "planned_outfits": sum(sum(v.values()) for v in supplied.values()),
                    "technical_ready_without_normalization": sum(r["technical_status"] == "raw_technical_ready" for r in rows),
                    "requires_authorized_normalization": sum(r["technical_status"] == "requires_authorized_normalization" for r in rows),
                    "errors": len(errors)},
        "target_coverage": {persona: dict(supplied[persona]) for persona in sorted(supplied)},
        "errors": errors,
        "entries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.plan.resolve())
    if args.output.exists():
        raise SystemExit("output exists; refusing overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False))
    if result["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

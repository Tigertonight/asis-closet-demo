#!/usr/bin/env python3
"""Rebind batch05 imagegen outputs by inspected content, never completion order."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.build_selfit_aw_generated_garment_batch05 import SPECS as UNBOUND_SPECS
from scripts.prepare_selfit_garment_asset import prepare


AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch06"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-targeted-04/garments"
SOURCE_ROOT = Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")

# These bindings were verified from the actual full-resolution pixels.  The
# previous batch inferred four bindings from file completion times and is not
# eligible for recommendation loading.
SOURCE_BY_ORIGINAL_TOKEN = {
    "n0018": "exec-bb098185-0e49-4d2d-8a4a-a4228740c3c0.png",
    "n0019": "exec-b7e67a5c-c0e6-4ebf-8093-72f3c03df4b5.png",
    "n0020": "exec-c3bfa959-129d-4059-a4fc-0d94c26a9ddf.png",
    "n0021": "exec-eee6e83c-d414-4266-ab42-4d4080991147.png",
    "n0022": "exec-b2a088f2-2ae1-4b41-91c6-0c8684e171ec.png",
    "n0023": "exec-b6f2aba1-f897-425c-b8f6-df0c27afd367.png",
    "n0024": "exec-1e8b336a-2fd6-403e-8ee9-15f29ce5cbb8.png",
    "n0025": "exec-d035b346-2abf-4285-8bc4-912635760359.png",
}


def corrected_specs() -> list[dict]:
    rows = copy.deepcopy(UNBOUND_SPECS)
    for offset, row in enumerate(rows, 26):
        old_token = row["token"]
        row["token"] = f"n{offset:04d}"
        row["id"] = row["id"].replace("targeted03", "targeted04").replace("_01", "_02")
        row["slug"] += "-content-bound"
        row["source_output"] = str(SOURCE_ROOT / SOURCE_BY_ORIGINAL_TOKEN[old_token])
    return rows


def main() -> None:
    specs = corrected_specs()
    for row in specs:
        source = Path(row["source_output"])
        raw = AUDIT / "raw" / f"{row['slug']}-raw-v1.png"
        prepared = AUDIT / "prepared" / f"{row['slug']}-v1.png"
        qa_path = AUDIT / "qa" / f"{row['slug']}-v1.json"
        stable_write(raw, source.read_bytes())
        if not prepared.exists():
            qa = prepare(raw, prepared)
            qa_path.parent.mkdir(parents=True, exist_ok=True)
            qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
    result = build(specs=specs, audit=AUDIT, static=STATIC,
                   batch_id="aw-generated-garments-06",
                   prompt_version="selfit-aw-targeted-content-bound-v2")
    result["supersedes_rejected_manifest"] = "generated-garments/batch05/manifest.json"
    result["binding_method"] = "individual_full_resolution_content_inspection"
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Corrected garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]),
                      "published": False, "binding": result["binding_method"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

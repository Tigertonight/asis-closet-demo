#!/usr/bin/env python3
"""Combine immutable generated-garment manifests for a cross-batch recipe review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
SOURCES = ["generated-garments/batch01/manifest.json", "generated-garments/batch02/manifest.json"]


def main() -> None:
    manifests = [json.loads((AUDIT / path).read_text()) for path in SOURCES]
    garments = [g for manifest in manifests for g in manifest["garments"]]
    if len({g["id"] for g in garments}) != len(garments):
        raise ValueError("Duplicate generated garment ID")
    visual = {gid: row for manifest in manifests for gid, row in manifest["visual"].items()}
    result = {"schema_version": 1, "batch_id": "aw-generated-garments-combined-01",
              "source_versions": [m["version"] for m in manifests], "status": "internal_candidate",
              "production_approved": False, "garments": garments, "visual": visual,
              "limitations": ["Aggregate manifest only; source manifests and assets remain immutable.",
                              "No garment is in the published pool."]}
    result["version"] = "aw-generated-garments-combined-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "generated-garments/combined-manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Combined manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(garments)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

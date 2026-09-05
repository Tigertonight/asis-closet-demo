#!/usr/bin/env python3
"""Combine all three immutable generated-garment batches for internal recipes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
SOURCES = [f"generated-garments/batch{index:02d}/manifest.json" for index in (1, 2, 3)]


def main() -> None:
    manifests = [json.loads((AUDIT / source).read_text()) for source in SOURCES]
    garments = [row for manifest in manifests for row in manifest["garments"]]
    if len({row["id"] for row in garments}) != len(garments):
        raise ValueError("Duplicate generated garment ID")
    visual = {garment_id: row for manifest in manifests for garment_id, row in manifest["visual"].items()}
    result = {"schema_version": 1, "batch_id": "aw-generated-garments-combined-02",
              "source_versions": [manifest["version"] for manifest in manifests],
              "status": "internal_candidate", "production_approved": False,
              "garments": garments, "visual": visual,
              "limitations": ["Aggregate manifest only; source assets remain immutable.",
                              "No garment is in the published pool."]}
    result["version"] = "aw-generated-garments-combined-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "generated-garments/combined-manifest-v2.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Combined manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(garments)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

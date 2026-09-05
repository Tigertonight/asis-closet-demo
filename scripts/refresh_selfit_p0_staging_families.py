"""Rebuild staged item family assignments before a fresh anchor selection."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import closet
from app.recommendation_diversity import FAMILY_PATH, style_family_map
from app.recommendation_visual import load_visual
from app.selfit_content_quality import record_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new staging output")
    source = args.staging.read_bytes()
    bundle = json.loads(source)
    pool = closet.selfit_content_pool()
    if (bundle.get("base_content_version") != pool.metadata.get("contentVersion")
            or bundle.get("visual_version") != load_visual().get("version")):
        raise ValueError("Content or visual revision changed; family-only refresh is insufficient")
    garments = list(pool.garments)
    for entry in bundle.get("staged_garments", []):
        if record_fingerprint(entry["record"]) != entry["record_fingerprint"]:
            raise ValueError("Staged garment fingerprint changed")
        garments.append(entry["record"])
    mapping = style_family_map(garments)
    for entry in bundle["entries"]:
        if record_fingerprint(entry["raw_record"]) != entry["record_fingerprint"]:
            raise ValueError("Staged outfit fingerprint changed")
        for item in entry["catalog_record"]["items"]:
            gid = item["item_id"]
            item["style_family_id"] = mapping.get(gid, "item:" + gid)
        entry["four_gate_status"] = "pending"
    bundle["previous_staging_sha256"] = hashlib.sha256(source).hexdigest()
    bundle["family_registry_sha256"] = hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest()
    bundle.pop("version", None)
    bundle["version"] = "p0-family-refresh-" + hashlib.sha256(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    print(bundle["version"])


if __name__ == "__main__":
    main()

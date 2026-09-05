"""Compile complete disposition ledger for all 83 focal-cohesion findings."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    ledger = json.loads((AUDIT / "repair-ledger.initial.json").read_text())
    reviews = []
    for batch in (5, 6):
        review = json.loads((AUDIT / f"repairs.batch0{batch}.native-review.json").read_text())
        reviews.extend((entry, f"aw-repair-0{batch}", review["version"]) for entry in review["entries"])
    review_by_token = {entry["source_token"]: (entry, batch, version) for entry, batch, version in reviews}
    source = [entry for entry in ledger["entries"] if entry["primary_group"] == "focal_cohesion"]
    assert len(source) == 83 and len(review_by_token) == 57

    entries = []
    review_versions = set()
    for item in source:
        token = item["token"]
        reviewed = review_by_token.get(token)
        if item["original_status"] == "suggested_exclude":
            decision = "exit_default"
            evidence = item["problem_evidence"]
            revision_batch = None
            next_review = "retain historical record; only reconsider under separately reviewed creative use"
        elif reviewed:
            observation, revision_batch, review_version = reviewed
            review_versions.add(review_version)
            if observation["status"] == "ai_candidate":
                decision = "repair_candidate"
                evidence = observation["evidence"]
                next_review = "internal recommendation validation only; not production approved"
            else:
                decision = "route_main_garment_recomposition"
                evidence = observation["evidence"]
                next_review = "replace or remove one competing main garment, rerender, then review whole outfit"
        else:
            decision = "superseded_parent_variant"
            evidence = "同一父配方已有另一条鞋包简化与整图复核记录；本版本不重复计算。"
            revision_batch = None
            next_review = "follow canonical parent disposition; do not count duplicate variant"
        entries.append({
            "outfit_id": item["outfit_id"], "token": token,
            "source_parent_recipe": item["source_parent_recipe"],
            "source_record_fingerprint": item["source_record_fingerprint"],
            "decision": decision, "revision_batch": revision_batch,
            "evidence": evidence,
            "counts_as_aw_daily_supply": decision == "repair_candidate",
            "original_preserved": True, "required_next_review": next_review,
        })

    counts = dict(sorted(Counter(entry["decision"] for entry in entries).items()))
    assert counts == {
        "exit_default": 18, "repair_candidate": 17,
        "route_main_garment_recomposition": 40, "superseded_parent_variant": 8,
    }
    result = {
        "schema_version": 1, "source_ledger_version": ledger["version"],
        "review_versions": sorted(review_versions), "entries": entries,
        "counts": counts, "production_approved": False,
    }
    result["version"] = "aw-focal-dispositions-" + digest(result)[:20]
    target = AUDIT / "focal-cohesion.dispositions.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Focal disposition ledger changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["version"])
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

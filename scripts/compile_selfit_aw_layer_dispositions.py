"""Compile complete disposition ledger for the 52 layer-structure findings.

This records evidence-bound decisions only. It does not mutate or publish outfits.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

FOCAL = {
    "o0107", "o0200", "o0260", "o0285", "o0289", "o0318", "o0401",
    "o0431", "o0462", "o0772", "o0901",
}
FOCAL_STRUCTURE = {"o0259", "o0859"}
WAIST = {"o0257", "o0352", "o0354", "o0732", "o0996"}
FOOTWEAR = {"o0137"}
PAIRED_SHOE_DISPLAY = {"o0507", "o0595", "o0950"}
EXIT_DEFAULT = {"o0170", "o0226", "o0433"}
SUPERSEDED_PARENT_VARIANT = {"o0171", "o0348", "o0729", "o0815", "o0816", "o0999"}


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    ledger = json.loads((AUDIT / "repair-ledger.initial.json").read_text())
    review = json.loads((AUDIT / "repairs.batch04.native-review.json").read_text())
    review_by_token = {entry["source_token"]: entry for entry in review["entries"]}
    source = [entry for entry in ledger["entries"] if entry["primary_group"] == "layer_structure"]
    assert len(source) == 52

    entries = []
    for item in source:
        token = item["token"]
        reviewed = review_by_token.get(token)
        revision_batch = "aw-repair-04" if reviewed else None

        if reviewed and reviewed["status"] == "ai_candidate":
            decision = "repair_candidate"
            evidence = reviewed["evidence"]
            counts_as_supply = True
            next_review = "internal recommendation validation only; not production approved"
        elif token in FOCAL:
            decision = "route_focal_recomposition"
            evidence = reviewed["evidence"] if reviewed else item["problem_evidence"]
            counts_as_supply = False
            next_review = "simplify competing focal garment or accessories, render, then review whole outfit"
        elif token in FOCAL_STRUCTURE:
            decision = "route_focal_and_layer_recomposition"
            evidence = item["problem_evidence"]
            counts_as_supply = False
            next_review = "resolve shoulder or layer volume and competing focal points together"
        elif token in WAIST:
            decision = "route_waist_structure_recomposition"
            evidence = item["problem_evidence"]
            counts_as_supply = False
            next_review = "remove redundant waist treatment, preserve one waistline, render and review"
        elif token in FOOTWEAR:
            decision = "route_footwear_formality_recomposition"
            evidence = item["problem_evidence"]
            counts_as_supply = False
            next_review = "replace footwear with daily-compatible pair and recheck layer volume"
        elif token in PAIRED_SHOE_DISPLAY:
            decision = "route_paired_shoe_display_repair"
            evidence = reviewed["evidence"]
            counts_as_supply = False
            next_review = "replace with a complete paired-shoe asset and rerender"
        elif token in EXIT_DEFAULT:
            decision = "exit_default"
            evidence = item["problem_evidence"]
            counts_as_supply = False
            next_review = "retain historical record; only reconsider in a separately reviewed creative scene"
        elif token in SUPERSEDED_PARENT_VARIANT:
            decision = "superseded_parent_variant"
            evidence = "同一父配方已有另一条处置记录；本条不重复计供给，历史版本保持可追溯。"
            counts_as_supply = False
            next_review = "follow the canonical parent disposition; do not count duplicate variant"
        else:
            raise AssertionError(f"Unclassified layer finding: {token}")

        entries.append({
            "outfit_id": item["outfit_id"],
            "token": token,
            "source_parent_recipe": item["source_parent_recipe"],
            "source_record_fingerprint": item["source_record_fingerprint"],
            "decision": decision,
            "revision_batch": revision_batch,
            "evidence": evidence,
            "counts_as_aw_daily_supply": counts_as_supply,
            "original_preserved": True,
            "required_next_review": next_review,
        })

    counts = dict(sorted(Counter(entry["decision"] for entry in entries).items()))
    assert sum(counts.values()) == 52
    assert counts["repair_candidate"] == 21
    result = {
        "schema_version": 1,
        "source_ledger_version": ledger["version"],
        "review_version": review["version"],
        "entries": entries,
        "counts": counts,
        "production_approved": False,
    }
    result["version"] = "aw-layer-dispositions-" + digest(result)[:20]
    target = AUDIT / "layer-structure.dispositions.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Layer disposition ledger changed; refusing to overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["version"])
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

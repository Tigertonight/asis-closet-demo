"""Compile explicit native family judgments into an OFFLINE, revision-bound draft.

No image inference happens here. Connected components and machine scores never
assign a family; TSV groups are the recorded native image decisions. No runtime
registry, garment QA state, content asset or recipe is modified.
"""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_profile import digest
from app.recommendation_visual import asset_sha
from app.selfit_content_quality import record_fingerprint
from app.closet import selfit_content_pool

DEFAULT = ROOT / "docs/audits/20260903-personal-home-visual/family-review"


def read_rows(directory):
    rows = []
    for path in sorted(directory.glob("native-groups-*.tsv")):
        with path.open() as handle:
            rows.extend({**r, "source_file": path.name} for r in csv.DictReader(handle, delimiter="\t"))
    return rows


def compile_review(visual, pool, manifest, rows, methods, historical, descriptors):
    assert manifest["visual_version"] == visual["version"], "Stale visual manifest"
    garments = visual["garments"]
    tokens = {r["token"]: gid for gid, r in garments.items()}
    records = {r["id"]: r for r in pool["garments"]}
    assert len(tokens) == len(garments), "Duplicate source tokens"
    assert methods["method"] == "explicit_group_based_native_visual_adjudication"
    assert methods["production_approved"] is False and methods["human_reviewed"] is False
    viewed_sheets = set(methods["sheets_viewed"])
    originals = set(methods["full_resolution_viewed"])
    assert originals <= tokens.keys(), "Unknown original image"
    expected = {m["token"]: m for m in manifest["members"]}
    assert len(expected) == len(manifest["members"]), "Duplicate manifest member"
    assert {m["sheet"] for m in expected.values()} <= viewed_sheets, "Unviewed contact sheet"
    assignments, groups = {}, defaultdict(list)
    for row in rows:
        assert row.get("group_id") and row.get("rationale") and row.get("boundary") and row.get("source_file")
        sources = row["source_sheets"].split(",")
        assert all(s in viewed_sheets or s.removeprefix("original:") in originals
                   and s.startswith("original:") for s in sources), "Unviewed evidence"
        for token in row["member_tokens"].split(","):
            assert token in tokens, f"Unknown member: {token}"
            assert token not in assignments, f"Duplicate assignment: {token}"
            assert (token in expected and expected[token]["sheet"] in sources
                    or f"original:{token}" in sources), f"Missing member image evidence: {token}"
            assignments[token] = row
            groups[row["group_id"]].append(token)
    assert expected.keys() <= assignments.keys(), "Incomplete machine member coverage"
    for token, row in expected.items():
        observation = garments[tokens[token]]
        assert row["garment_id"] == tokens[token]
        assert all(row[k] == observation[k] for k in ("record_fingerprint", "asset_sha256", "image_url")), "Stale member manifest"
    for token in assignments:
        gid = tokens[token]
        assert record_fingerprint(records[gid]) == garments[gid]["record_fingerprint"], "Stale content record"

    families, ledger = [], []
    for name, members in sorted(groups.items()):
        assert len({garments[tokens[t]]["observations"]["category"] for t in members}) == 1, "Cross-category family"
        evidence = [dict(source_file=r["source_file"], rationale=r["rationale"], boundary=r["boundary"],
                         sources=r["source_sheets"].split(","))
                    for r in rows if r["group_id"] == name]
        if len(members) >= 2:
            families.append({"id": "native:" + name, "status": "visual_reviewed",
                "reviewer": methods["reviewer"], "evidence": evidence,
                "members": {tokens[t]: garments[tokens[t]]["record_fingerprint"] for t in sorted(members)},
                "asset_sha256": {tokens[t]: garments[tokens[t]]["asset_sha256"] for t in sorted(members)},
                "semantics": "repeat_exposure_family_not_identical_sku", "production_approved": False})
        for token in sorted(members):
            g = garments[tokens[token]]
            ledger.append({"token": token, "garment_id": tokens[token], "group_id": name,
                "family_id": "native:" + name if len(members) >= 2 else None,
                "family_status": "native_visual_family_draft" if len(members) >= 2 else "no_family_confirmed_in_candidate_set",
                "qa_status_unchanged": g["status"], "record_fingerprint": g["record_fingerprint"],
                "asset_sha256": g["asset_sha256"], "source_file": assignments[token]["source_file"],
                "rationale": assignments[token]["rationale"], "boundary": assignments[token]["boundary"]})

    def decision(left, right):
        assert left in assignments and right in assignments, "Unreviewed comparison member"
        a, b = assignments[left], assignments[right]
        return {"left": tokens[left], "right": tokens[right], "left_token": left, "right_token": right,
                "decision": "same_visual_family" if a["group_id"] == b["group_id"] else "distinct_visual_family",
                "left_group": a["group_id"], "right_group": b["group_id"],
                "evidence": [{"token": t, "rationale": assignments[t]["rationale"],
                    "boundary": assignments[t]["boundary"], "source_file": assignments[t]["source_file"],
                    "asset_sha256": garments[tokens[t]]["asset_sha256"],
                    "record_fingerprint": garments[tokens[t]]["record_fingerprint"]} for t in (left, right)]}

    queue, seen = [], set()
    for pair in manifest["pairs"]:
        key = tuple(sorted((pair["left"], pair["right"])))
        assert key[0] != key[1] and key not in seen, "Duplicate machine pair"
        seen.add(key)
        queue.append({**decision(garments[key[0]]["token"], garments[key[1]]["token"]),
                      "candidate_source": "historical_mask_and_color_queue", "machine_candidate": pair})
    assert len(queue) == manifest["pair_count"], "Pair count mismatch"
    reconciled = []
    for note in historical:
        ds = [decision(a, b) for a, b in combinations(note["member_tokens"].split(","), 2)]
        reconciled.append({"historical_note": note, "decisions": ds,
            "outcome": "confirmed_visual_family" if all(d["decision"] == "same_visual_family" for d in ds)
                       else "split_preserving_shared_design_language"})
    descriptor_reviews = [{"descriptor_id": group["id"],
        "decisions": [decision(a["token"], b["token"]) for a, b in combinations(group["members"], 2)]}
        for group in descriptors]
    unpaired = [{"garment_id": gid, "token": g["token"], "qa_status_unchanged": g["status"],
                 "family_status": "not_in_current_pair_candidate_set_recall_unknown"}
                for gid, g in garments.items() if g["token"] not in assignments]
    version = "native-family-" + digest([visual["version"], manifest["pairs"], rows, methods, historical, descriptors])[:20]
    registry = {"schema_version": 1, "version": version, "visual_version": visual["version"],
                "policy": "OFFLINE DRAFT ONLY. No production activation or QA promotion.",
                "production_approved": False, "families": families}
    report = {"schema_version": 1, "version": version, "visual_version": visual["version"],
        "methods": methods, "counts": {"machine_pairs": len(queue), "machine_members": len(expected),
            "reviewed_members": len(ledger), "draft_families": len(families),
            "family_members": sum(len(f["members"]) for f in families), "comparison_singletons": sum(r["family_id"] is None for r in ledger),
            "not_in_comparison_set": len(unpaired), "pair_decisions": dict(Counter(d["decision"] for d in queue)),
            "historical_notes": len(reconciled), "descriptor_groups": len(descriptor_reviews)},
        "machine_pairs_all_adjudicated": True, "exhaustive_all_pairs_recall": None,
        "production_approved": False, "registry_activated": False, "member_ledger": ledger,
        "not_in_comparison_set": unpaired, "machine_pair_decisions": queue,
        "historical_reconciliation": reconciled, "descriptor_reconciliation": descriptor_reviews}
    return registry, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    args = parser.parse_args()
    directory = args.directory
    read = lambda p: json.loads(p.read_text())
    visual = read(ROOT / "app/data/recommendation-visual.v1.json")
    rows = read_rows(directory)
    # Check bytes, not only a previously recorded digest.
    token_records = {g["token"]: g for g in visual["garments"].values()}
    for token in {t for row in rows for t in row["member_tokens"].split(",")}:
        g = token_records[token]
        assert asset_sha(g["image_url"]) == g["asset_sha256"], f"Stale asset: {token}"
    notes = []
    for path in sorted(directory.parent.glob("codex-family-observations-*.tsv")):
        with path.open() as handle:
            notes.extend({**r, "source_file": path.name} for r in csv.DictReader(handle, delimiter="\t"))
    descriptors = read(directory.parent / "full-native-audit-summary.json")["family_governance"]["strict_descriptor_candidates"]
    # Fingerprints bind the effective curated records, not the unpatched source JSON.
    registry, report = compile_review(visual,
        {"garments": selfit_content_pool().garments}, read(directory / "manifest.json"),
        rows, read(directory / "methods.json"), notes, descriptors)
    report["source_file_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.glob("native-groups-*.tsv")) + [directory / "methods.json", directory / "manifest.json"]}
    for name, data in (("garment-style-families.native-draft.json", registry), ("native-family-review.json", report)):
        (directory / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": report["version"], **report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

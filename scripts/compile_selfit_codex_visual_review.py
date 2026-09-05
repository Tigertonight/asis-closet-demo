"""Compile explicit native Codex judgments; looking at a sheet is not approval.

No image model is invoked and no labels are inferred by this script. Unknown
fields remain unknown. Source journals, assets and record revisions are bound
to every result so a changed asset requires a fresh review.
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool
from app.recommendation_profile import PERSONAS, digest
from app.recommendation_visual import EXPRESSIONS, FIELDS, asset_sha
from app.selfit_content_quality import record_fingerprint


def compile_review(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    sources = [directory / "codex-first-pass.json", *sorted(directory.glob("codex-outfits-*.json"))]
    journals = {p.name: json.loads(p.read_text()) for p in sources}
    sheets = {"garments": {}, "outfits": {}}
    for name, journal in journals.items():
        for section, key in (("garments", "garment_sheets"), ("outfits", "outfit_sheets")):
            for sheet in journal.get(key, []):
                assert sheet["sheet"] not in sheets[section], "Duplicate sheet judgment"
                sheets[section][sheet["sheet"]] = (name, sheet)
    pool = selfit_content_pool()
    current = {"garments": {g["id"]: g for g in pool.garments}, "outfits": {o["id"]: o for o in pool.outfits}}
    result = {"schema_version": 1, "reviewer": "current_codex_session",
              "status": "partial_semantic_validation", "human_reviewed": False,
              "independent_blind_review": False, "publish_approval": False,
              "confidence_interpretation": "AI subjective triage confidence, not calibrated accuracy",
              "source_digest": digest(journals), "garments": {}, "outfits": {}}
    by_token = {}
    for section in sheets:
        assert set(current[section]) == set(manifest[section]), "Pool changed: prepare a new audit"
        seen = set()
        for rid, original in manifest[section].items():
            token = original["token"]
            number = int(token[1:])
            sheet_number = int(original["sheet"].split("-")[1].split(".")[0])
            name, sheet = sheets[section][sheet_number]
            assert sheet["tokens"][0] <= number <= sheet["tokens"][1]
            assert original["record_fingerprint"] == record_fingerprint(current[section][rid]), rid
            assert original["asset_sha256"] == asset_sha(original["image_url"]), rid
            assert token not in seen
            seen.add(token)
            record = {**original, "status": "needs_review", "source_kind": "codex_visual_review",
                      "model": "current_codex_session", "prompt_version": "native-visual-audit-v1",
                      "confidence": .6, "review_level": "contact_sheet_first_pass",
                      "evidence": sheet["evidence"], "evidence_scope": "sheet_not_individual_attribute_confirmation",
                      "source_file": name, "observations": {key: None for key in sorted(FIELDS[section])}}
            result[section][rid] = record
            by_token[token] = record
        expected = {f"{section[0]}{n:04d}" for _, s in sheets[section].values() for n in range(s["tokens"][0], s["tokens"][1]+1)}
        assert seen == expected, "Missing or excess sheet tokens"

    with (directory / "codex-garment-candidates.tsv").open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            record = by_token[row.pop("token")]
            record.update(status="ai_candidate", confidence=.8, review_level="individual_contact_sheet_judgment",
                          evidence=row.pop("evidence"), evidence_scope="individual_visual_judgment",
                          source_file="codex-garment-candidates.tsv")
            record["observations"].update({k: None if v == "unknown" else v for k, v in row.items()})
    candidates = json.loads((directory / "codex-outfit-candidates.json").read_text())
    for token, judgment in candidates["outfits"].items():
        record = by_token[token]
        record.update(status=judgment.get("status", "ai_candidate"), confidence=.8,
                      review_level="individual_contact_sheet_judgment", evidence=judgment["evidence"],
                      evidence_scope="nonblind_individual_visual_judgment",
                      source_file="codex-outfit-candidates.json")
        record["observations"].update({k: v for k, v in judgment.items() if k in FIELDS["outfits"]})
        record["observations"]["axes"] = {}  # not calibrated from production prompts
    for token, judgment in candidates["detail_exclusions"].items():
        by_token[token].update(status="suggested_exclude", confidence=.9,
                              review_level="full_resolution_detail", evidence=judgment["evidence"],
                              evidence_scope="default_daily_validation_only",
                              exclusion_reason=judgment["reason"], source_file="codex-outfit-candidates.json")

    # New batches contain an explicit judgment for EVERY named item. They may
    # refine pilot judgments, but must not silently overwrite another batch.
    batch_tokens = set()
    methods_path = directory / "codex-semantic-methods.json"
    methods = json.loads(methods_path.read_text()) if methods_path.exists() else {}
    detail_tokens = set(methods.get("full_resolution_tokens", []))
    assert len(detail_tokens) == len(methods.get("full_resolution_tokens", [])), "Duplicate detail review token"
    for batch in sorted(directory.glob("codex-semantic-garments-*.tsv")):
        with batch.open() as handle:
            for raw_row in csv.DictReader(handle, delimiter="\t"):
                assert None not in raw_row and all(v is not None for v in raw_row.values()), f"Malformed row in {batch.name}"
                row = {k: v.strip() for k, v in raw_row.items()}
                token = row.pop("token")
                assert token.startswith("g") and token in by_token and token not in batch_tokens, token
                batch_tokens.add(token)
                record = by_token[token]
                assert row["status"] in {"ai_candidate", "needs_review", "suggested_exclude"}
                assert row["category"] in {"top", "outer", "bottom", "skirt", "dress", "shoes", "bag", "hat", "scarf", "accessory"}, token
                assert len(row["evidence"]) >= 20, token
                record["previous_judgment"] = {k: record.get(k) for k in ("source_file", "status", "evidence", "review_level")}
                record.update(status=row.pop("status"), evidence=row.pop("evidence"), confidence=.8,
                              review_level="full_resolution_detail" if token in detail_tokens else "individual_contact_sheet_judgment", evidence_scope="individual_visual_judgment",
                              source_file=batch.name, prompt_version="native-visual-audit-v2")
                for name in ("main_colors", "visual_personas", "usage_limits"):
                    value = row.pop(name)
                    record["observations"][name] = None if value == "unknown" else [s.strip() for s in value.replace(";", ",").split(",")]
                record["observations"].update({k: None if v == "unknown" else v for k, v in row.items()})
                assert set(record["observations"].get("visual_personas") or []) <= set(PERSONAS), token
                record["review_complete"] = True
                record["confidence_basis"] = "Non-calibrated AI visual judgment; unknown fields remain null. Asset candidate is not outfit or daily-use approval."

    for batch in sorted(directory.glob("codex-semantic-outfits-*.tsv")):
        with batch.open() as handle:
            for raw_row in csv.DictReader(handle, delimiter="\t"):
                assert None not in raw_row and all(v is not None for v in raw_row.values()), f"Malformed row in {batch.name}"
                row = {k: v.strip() for k, v in raw_row.items()}
                token = row.pop("token")
                assert token.startswith("o") and token in by_token and token not in batch_tokens, token
                batch_tokens.add(token)
                record = by_token[token]
                assert row["status"] in {"ai_candidate", "needs_review", "suggested_exclude"}
                assert row["structure"] in {"pants", "skirt", "dress"}
                assert row["expression"] in EXPRESSIONS, f"Unknown expression for {token}"
                assert len(row["evidence"]) >= 20 and row["persona_evidence"], token
                record["previous_judgment"] = {k: record.get(k) for k in ("source_file", "status", "evidence", "review_level")}
                record.update(status=row.pop("status"), evidence=row.pop("evidence"), confidence=.8,
                              review_level="full_resolution_detail" if token in detail_tokens else "individual_contact_sheet_judgment",
                              evidence_scope="nonblind_individual_visual_judgment", source_file=batch.name,
                              prompt_version="native-visual-audit-v2", review_complete=True)
                scores = json.loads(row.pop("persona_scores"))
                assert set(scores) <= set(PERSONAS), token
                assert scores and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 1 for v in scores.values()), token
                record["observations"].update(persona_scores=scores, axes={}, layering=int(row.pop("layering")))
                for name in ("main_visual_slots", "main_colors", "seasons", "scenes", "conflicts"):
                    value = row.pop(name)
                    record["observations"][name] = None if value == "unknown" else [s.strip() for s in value.split(",")]
                assert set(record["observations"]["seasons"] or []) <= {"spring", "summer", "autumn", "winter"}, token
                assert set(record["observations"]["scenes"] or []) <= {"daily", "commute", "social", "formal", "travel", "creative"}, token
                record["observations"].update({k: None if v == "unknown" else v for k, v in row.items()})
                record["confidence_basis"] = "Nonblind AI judgment of the actual cover. Persona affinities are uncalibrated; no inferred body, skin or weather fit."
    assert detail_tokens <= batch_tokens, "Detail review token missing its explicit judgment"
    for section in sheets:
        for record in result[section].values():
            record["field_status"] = {k: "unknown" if v is None or v == {} else "ai_observed"
                                      for k, v in record["observations"].items()}
            record["field_provenance"] = {k: {"source_file": record["source_file"], "version": record["prompt_version"],
                                              "confidence": None if status == "unknown" else record["confidence"]}
                                          for k, status in record["field_status"].items()}
    result["completion"] = {s: {"total": len(result[s]),
                               "individual_judgments": sum(r["review_level"] != "contact_sheet_first_pass" for r in result[s].values()),
                               "full_field_reviews": sum(r.get("review_complete", False) for r in result[s].values())}
                            for s in sheets}
    result["counts"] = {s: dict(Counter(r["status"] for r in result[s].values())) for s in sheets}
    if all(c["full_field_reviews"] == c["total"] for c in result["completion"].values()):
        # Completeness is about explicit records, never approval or blind accuracy.
        result["status"] = "full_semantic_review_recorded"
    result["version"] = "codex-visual-" + digest(result)[:20]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compile_review(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"version": result["version"], "counts": result["counts"]}, ensure_ascii=False))

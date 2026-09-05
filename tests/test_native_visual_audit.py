"""Audit scope checks: notes cannot silently become approvals or fake completion."""
import csv
from pathlib import Path
import pytest

from scripts.compile_selfit_codex_visual_review import compile_review

AUDIT = Path(__file__).resolve().parents[1] / "docs/audits/20260903-personal-home-visual"


def test_explicit_batches_have_complete_token_provenance():
    result = compile_review(AUDIT)
    assert result["publish_approval"] is False and result["independent_blind_review"] is False
    for section in ("garments", "outfits"):
        tokens = []
        for path in AUDIT.glob(f"codex-semantic-{section}-*.tsv"):
            with path.open() as handle:
                tokens.extend(r["token"] for r in csv.DictReader(handle, delimiter="\t"))
        assert len(tokens) == len(set(tokens))
        records = {r["token"]: r for r in result[section].values()}
        assert result["completion"][section]["full_field_reviews"] == len(tokens)
        for token in tokens:
            record = records[token]
            assert record["review_complete"] and record["asset_sha256"] and record["record_fingerprint"]
            assert record["evidence_scope"] != "sheet_not_individual_attribute_confirmation"
            for key, status in record["field_status"].items():
                provenance = record["field_provenance"][key]
                assert provenance["source_file"].startswith("codex-semantic-")
                if status == "unknown":
                    assert provenance["confidence"] is None
        for record in records.values():
            if record["review_level"] == "contact_sheet_first_pass":
                assert record["status"] == "needs_review"
                assert not record.get("review_complete")


def test_detailed_review_preserves_conflicts_and_correct_structure():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    # Looks like a long skirt in a thumbnail, but the full image shows two legs.
    assert outfits["o0020"]["observations"]["structure"] == "pants"
    for token in ("o0017", "o0020", "o0021", "o0023"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "needs_review"
        assert outfits[token]["observations"]["conflicts"]
        assert outfits[token]["observations"]["axes"] == {}
    garments = {r["token"]: r for r in result["garments"].values()}
    assert garments["g0080"]["review_level"] == "full_resolution_detail"
    assert garments["g0080"]["status"] == "needs_review"
    for token in ("o0044", "o0052", "o0070"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "needs_review"
    assert outfits["o0049"]["review_level"] == "full_resolution_detail"
    assert outfits["o0049"]["status"] == "ai_candidate"
    for token in ("o0107", "o0111"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    assert outfits["o0110"]["status"] == "suggested_exclude"
    assert "multiple_focal_overload" in outfits["o0110"]["observations"]["conflicts"]
    for token in ("o0125", "o0128"):
        assert outfits[token]["observations"]["structure"] == "pants"
        assert outfits[token]["review_level"] == "full_resolution_detail"
    assert outfits["o0140"]["status"] == "suggested_exclude"
    assert "multiple_focal_overload" in outfits["o0140"]["observations"]["conflicts"]
    assert outfits["o0144"]["status"] == "suggested_exclude"
    assert "season_balance_unresolved" in outfits["o0144"]["observations"]["conflicts"]
    # Replacing only accessories must not silently approve the same conflict.
    assert outfits["o0148"]["status"] == "suggested_exclude"
    assert "season_balance_unresolved" in outfits["o0148"]["observations"]["conflicts"]
    for token in ("g0343", "g0354", "g0359"):
        assert garments[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in garments[token]["observations"]["usage_limits"]
    assert outfits["o0186"]["status"] == "needs_review"
    assert "opaque_inner_unverified" in outfits["o0186"]["observations"]["conflicts"]
    assert outfits["o0201"]["review_level"] == "full_resolution_detail"
    assert outfits["o0201"]["observations"]["structure"] == "pants"
    assert outfits["o0201"]["status"] == "suggested_exclude"
    assert "missing_opaque_inner" in outfits["o0201"]["observations"]["conflicts"]
    assert outfits["o0203"]["status"] == "suggested_exclude"
    assert outfits["o0203"]["previous_judgment"]["status"] == "suggested_exclude"
    # A plain ankle boot is not the same observed conflict as a snow boot.
    assert outfits["o0207"]["review_level"] == "full_resolution_detail"
    assert outfits["o0207"]["status"] == "ai_candidate"
    assert outfits["o0212"]["observations"]["structure"] == "pants"
    assert outfits["o0212"]["status"] == "needs_review"
    assert outfits["o0217"]["observations"]["structure"] == "pants"
    for token in ("o0226", "o0229"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    assert outfits["o0231"]["status"] == "needs_review"
    assert "multiple_focal_overload" not in outfits["o0231"]["observations"]["conflicts"]
    assert garments["g0423"]["review_level"] == "full_resolution_detail"
    assert garments["g0423"]["observations"]["category"] == "bottom"
    assert garments["g0425"]["status"] == "needs_review"
    assert "opaque_lining_unverified" in garments["g0425"]["observations"]["usage_limits"]
    assert outfits["o0269"]["observations"]["structure"] == "pants"
    assert outfits["o0279"]["status"] == "needs_review"
    assert "opaque_inner_unverified" in outfits["o0279"]["observations"]["conflicts"]
    assert outfits["o0282"]["review_level"] == "full_resolution_detail"
    assert outfits["o0282"]["status"] == "suggested_exclude"
    assert "missing_opaque_inner" in outfits["o0282"]["observations"]["conflicts"]
    # A narrow inner top does not inherit the large puff-sleeve conflict.
    assert outfits["o0285"]["status"] == "needs_review"
    assert outfits["o0286"]["status"] == "ai_candidate"
    for token in ("o0289", "o0318"):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    # Changing a conflicting accessory can make an occasion look viable,
    # but must not turn a theatrical gown into an everyday recommendation.
    assert outfits["o0291"]["status"] == "ai_candidate"
    assert outfits["o0291"]["observations"]["wearability"] == "statement_not_daily"
    assert outfits["o0319"]["status"] == "ai_candidate"
    assert outfits["o0328"]["review_level"] == "full_resolution_detail"
    assert outfits["o0328"]["observations"]["persona_scores"]["jade"] < 0.55
    assert outfits["o0332"]["observations"]["persona_scores"]["jade"] >= 0.55


def test_compilation_is_reproducible():
    assert compile_review(AUDIT)["version"] == compile_review(AUDIT)["version"]


def test_completed_garment_review_does_not_approve_unresolved_structure():
    result = compile_review(AUDIT)
    assert result["completion"]["garments"]["full_field_reviews"] == 600
    garments = {r["token"]: r for r in result["garments"].values()}
    assert garments["g0562"]["status"] == "ai_candidate"
    assert garments["g0567"]["status"] == "needs_review"
    assert "opaque_inner_unverified" in garments["g0567"]["observations"]["usage_limits"]
    assert garments["g0573"]["status"] == "needs_review"
    assert "single_garment_structure_unverified" in garments["g0573"]["observations"]["usage_limits"]
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0345", "o0346", "o0348", "o0349", "o0356"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["observations"]["structure"] == "pants"
    assert outfits["o0348"]["status"] == "needs_review"
    assert outfits["o0349"]["status"] == "ai_candidate"
    assert outfits["o0359"]["status"] == "ai_candidate"
    for token in ("o0352", "o0354"):
        assert "duplicate_waist_styling_unresolved" in outfits[token]["observations"]["conflicts"]
        assert outfits[token]["status"] == "needs_review"
    # Quiet overlap/stand-collar construction can support JADE without ink prints.
    assert outfits["o0331"]["observations"]["persona_scores"]["jade"] >= 0.55
    assert outfits["o0383"]["observations"]["persona_scores"]["neon"] < 0.55


def test_detail_review_separates_statement_pieces_from_focal_overload():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0398", "o0448", "o0455"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
        # Sheer sleeves or decorative lace do not by themselves prove a missing bodice.
        assert "missing_opaque_inner" not in outfits[token]["observations"]["conflicts"]
    for token in ("o0417", "o0432", "o0433", "o0441", "o0450", "o0460"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    for token in ("o0391", "o0411", "o0423", "o0442", "o0447", "o0458", "o0468"):
        assert outfits[token]["status"] == "ai_candidate"
    assert outfits["o0413"]["status"] == "needs_review"
    assert outfits["o0467"]["status"] == "needs_review"
    assert outfits["o0468"]["observations"]["wearability"] == "statement_not_daily"
    assert "daily" not in outfits["o0468"]["observations"]["scenes"]
    for token in ("o0441", "o0442", "o0447", "o0448", "o0477", "o0478"):
        assert outfits[token]["observations"]["structure"] == "pants"
    assert outfits["o0450"]["observations"]["structure"] == "skirt"


def test_replacements_do_not_hide_coverage_layering_or_persona_gaps():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0401", "o0402", "o0434", "o0461", "o0462"):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0391", "o0459", "o0471", "o0472"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    assert outfits["o0480"]["status"] == "needs_review"
    assert "opaque_inner_unverified" in outfits["o0480"]["observations"]["conflicts"]
    assert outfits["o0410"]["status"] == "needs_review"
    assert "daily" not in outfits["o0410"]["observations"]["scenes"]
    # Bright or patchwork accessories cannot substitute for main-garment evidence.
    for token in ("o0444", "o0451", "o0452", "o0459", "o0464"):
        assert outfits[token]["observations"]["persona_scores"]["oops"] < 0.55
    assert outfits["o0458"]["observations"]["persona_scores"]["neon"] >= 0.55
    assert outfits["o0442"]["observations"]["persona_scores"]["oops"] >= 0.55


def test_detail_review_distinguishes_opaque_bodices_and_real_sleeve_capacity():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0516", "o0526", "o0536"):
        assert outfits[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    # Changing the actual top can resolve coverage; changing shoes cannot.
    for token in ("o0517", "o0527", "o0537", "o0525", "o0545", "o0550"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0507", "o0547"):
        assert outfits[token]["review_level"] == "full_resolution_detail"
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    # A roomy bomber or sleeveless inner is not the fitted-shell/large-sleeve case.
    for token in ("o0506", "o0548", "o0549"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    assert outfits["o0489"]["observations"]["structure"] == "skirt"
    for token in ("o0502", "o0503", "o0504"):
        assert outfits[token]["observations"]["structure"] == "pants"
    # Unlike the earlier self-belted dress case, this dress has no second belt.
    assert outfits["o0510"]["status"] == "ai_candidate"
    assert "duplicate_waist_styling_unresolved" not in (outfits["o0510"]["observations"]["conflicts"] or [])


def test_main_garment_evidence_does_not_reject_balanced_statement_looks():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0512", "o0557"):
        assert outfits[token]["status"] == "needs_review"
        assert "occasion_accessory_balance_unresolved" in outfits[token]["observations"]["conflicts"]
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0500", "o0544", "o0563", "o0573"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "multiple_focal_overload" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0563", "o0573"):
        assert outfits[token]["observations"]["persona_scores"]["bolt"] >= 0.55
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0530", "o0540"):
        assert outfits[token]["observations"]["persona_scores"]["iced"] < 0.55
    for token in ("o0566", "o0570", "o0576"):
        assert outfits[token]["observations"]["persona_scores"]["jade"] < 0.55
    assert outfits["o0576"]["observations"]["persona_scores"]["bolt"] < 0.55
    assert outfits["o0486"]["observations"]["persona_scores"]["noir"] >= 0.55
    assert outfits["o0500"]["observations"]["persona_scores"]["jade"] >= 0.55


def test_soft_layers_do_not_inherit_unrelated_coverage_and_volume_issues():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0595",):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0591", "o0594", "o0596", "o0635", "o0636", "o0638", "o0639"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0648", "o0655", "o0658", "o0668", "o0670", "o0671"):
        assert outfits[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    # The layered blouse with a visible core and opaque small-floral blouse
    # are different assets from the unresolved sheer blouse, not title variants.
    for token in ("o0633", "o0636", "o0638", "o0639", "o0650", "o0651", "o0659", "o0664", "o0665", "o0669"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    assert outfits["o0660"]["status"] == "needs_review"
    assert "season_layering_unresolved" in outfits["o0660"]["observations"]["conflicts"]
    assert outfits["o0660"]["observations"]["seasons"] is None
    assert outfits["o0661"]["status"] == "ai_candidate"


def test_native_review_keeps_style_evidence_separate_from_color_and_accessories():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0605", "o0611", "o0621", "o0624", "o0643", "o0644"):
        assert outfits[token]["observations"]["persona_scores"]["wabi"] < 0.55
    for token in ("o0604", "o0610", "o0620", "o0623", "o0640"):
        assert outfits[token]["observations"]["persona_scores"]["wabi"] >= 0.55
    assert outfits["o0634"]["status"] == "needs_review"
    assert "multiple_focal_competition" in outfits["o0634"]["observations"]["conflicts"]
    assert outfits["o0637"]["status"] == "suggested_exclude"
    assert "multiple_focal_overload" in outfits["o0637"]["observations"]["conflicts"]
    for token in ("o0640", "o0642", "o0650", "o0659"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0634", "o0635", "o0637", "o0650", "o0651", "o0658", "o0664", "o0665"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o0589", "o0590", "o0670", "o0671"):
        assert outfits[token]["observations"]["structure"] == "skirt"
    for token in ("o0578", "o0579"):
        assert outfits[token]["review_level"] == "full_resolution_detail"


def test_native_review_checks_layer_capacity_and_waist_details_per_recipe():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0680", "o0684", "o0728", "o0729"):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0679", "o0681", "o0683", "o0724", "o0725", "o0726"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0677", "o0684", "o0736"):
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0675", "o0676", "o0683", "o0685", "o0687", "o0726", "o0740"):
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0686", "o0690"):
        assert outfits[token]["status"] == "needs_review"
        assert "season_layering_unresolved" in outfits[token]["observations"]["conflicts"]
        assert outfits[token]["observations"]["seasons"] is None
    assert "duplicate_waist_styling_unresolved" in outfits["o0732"]["observations"]["conflicts"]
    assert outfits["o0688"]["status"] == "ai_candidate"
    assert "duplicate_waist_styling_unresolved" not in (outfits["o0688"]["observations"]["conflicts"] or [])


def test_native_review_distinguishes_controlled_experiment_from_focal_overload():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0682", "o0727"):
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    assert outfits["o0739"]["status"] == "needs_review"
    assert "multiple_focal_competition" in outfits["o0739"]["observations"]["conflicts"]
    assert outfits["o0734"]["status"] == "needs_review"
    assert "occasion_accessory_balance_unresolved" in outfits["o0734"]["observations"]["conflicts"]
    for token in ("o0685", "o0687", "o0689", "o0703", "o0704", "o0713", "o0722", "o0738", "o0740"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0682", "o0724", "o0725", "o0726", "o0738", "o0739"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o0678", "o0711", "o0713", "o0721", "o0722"):
        assert outfits[token]["observations"]["structure"] == "skirt"


def test_plain_neutrals_do_not_borrow_distressed_accessory_persona_evidence():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0692", "o0698", "o0699", "o0700", "o0702", "o0705", "o0706", "o0709", "o0710", "o0715", "o0716", "o0717", "o0718", "o0719", "o0720", "o0723", "o0730", "o0731", "o0733", "o0735"):
        assert outfits[token]["observations"]["persona_scores"]["wabi"] < 0.55
    for token in ("o0693", "o0694", "o0695", "o0697", "o0708", "o0711", "o0712", "o0713", "o0714", "o0721", "o0722"):
        assert outfits[token]["observations"]["persona_scores"]["wabi"] >= 0.55
    for token in ("o0737", "o0743", "o0744"):
        assert outfits[token]["observations"]["persona_scores"]["flou"] < 0.55


def test_late_flou_neon_review_keeps_specific_cover_and_layering_evidence():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0746", "o0756", "o0766"):
        assert outfits[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0750", "o0767", "o0768", "o0771", "o0773", "o0792"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0769", "o0772", "o0814", "o0815", "o0816"):
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
        assert outfits[token]["review_level"] == "full_resolution_detail"
    for token in ("o0768", "o0770", "o0771", "o0811", "o0812"):
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    assert outfits["o0776"]["observations"]["seasons"] is None
    assert outfits["o0778"]["status"] == "ai_candidate"
    for token in ("o0796", "o0797", "o0814"):
        assert "paired_heel_balance_unverified" in outfits[token]["observations"]["conflicts"]
    # Removing the high-color shirt reduces overload, but does not fix the boot.
    assert outfits["o0797"]["observations"]["conflicts"] == ["paired_heel_balance_unverified"]


def test_high_expression_is_not_a_blanket_rejection_or_daily_approval():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0786", "o0796", "o0809", "o0811", "o0814"):
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    for token in ("o0780", "o0785", "o0795", "o0798", "o0813"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
    for token in ("o0784", "o0787", "o0792", "o0808", "o0810", "o0812"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    assert "occasion_accessory_balance_unresolved" in outfits["o0775"]["observations"]["conflicts"]
    for token in ("o0798", "o0802", "o0803", "o0808", "o0809", "o0810"):
        assert outfits[token]["observations"]["structure"] == "skirt"


def test_neon_template_does_not_override_actual_main_clothing_evidence():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0781", "o0782", "o0783", "o0788", "o0789", "o0790", "o0791", "o0793", "o0794", "o0799", "o0800", "o0801", "o0802", "o0803", "o0804", "o0805", "o0806", "o0807"):
        assert outfits[token]["observations"]["persona_scores"]["neon"] < 0.55
    for token in ("o0784", "o0792", "o0815"):
        assert outfits[token]["observations"]["persona_scores"]["edge"] >= 0.55
        assert outfits[token]["observations"]["persona_scores"]["neon"] < 0.55
    for token in ("o0808", "o0810"):
        assert outfits[token]["observations"]["persona_scores"]["neon"] >= 0.85
        assert outfits[token]["status"] == "ai_candidate"


def test_edge_series_review_distinguishes_accessory_competition_from_overload():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0827", "o0855", "o0857"):
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    for token in ("o0828", "o0841", "o0859"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
    for token in ("o0820", "o0821", "o0829", "o0830", "o0834", "o0835", "o0839", "o0842", "o0844", "o0853", "o0854", "o0856", "o0858", "o0860", "o0862"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0835", "o0836", "o0841", "o0842"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o0829", "o0839", "o0853"):
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0859", "o0861"):
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0856", "o0857", "o0858", "o0860"):
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    assert outfits["o0861"]["status"] == "needs_review"
    assert "paired_heel_balance_unverified" in outfits["o0861"]["observations"]["conflicts"]
    assert "multiple_focal_overload" not in outfits["o0861"]["observations"]["conflicts"]


def test_black_or_blue_basics_do_not_inherit_their_edge_series_name():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0823", "o0831", "o0832", "o0837", "o0838", "o0840", "o0845", "o0846", "o0847", "o0848", "o0849", "o0850", "o0851", "o0852", "o0863", "o0864"):
        assert outfits[token]["observations"]["persona_scores"]["edge"] < 0.55
    for token in ("o0820", "o0829", "o0839", "o0842", "o0843", "o0844", "o0853", "o0854", "o0862"):
        assert outfits[token]["observations"]["persona_scores"]["edge"] >= 0.55
    for token in ("o0817", "o0818", "o0819", "o0822", "o0831", "o0832"):
        assert outfits[token]["observations"]["persona_scores"]["neon"] < 0.55
    for token in ("o0821", "o0830", "o0833", "o0834", "o0856", "o0858"):
        assert outfits[token]["observations"]["persona_scores"]["neon"] >= 0.55


def test_bolt_replacements_preserve_coverage_and_layering_caveats():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0875", "o0883", "o0885", "o0895", "o0903", "o0904"):
        assert outfits[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0869", "o0879", "o0898", "o0909"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0901", "o0902"):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0877", "o0893", "o0900", "o0905"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0878", "o0879", "o0883", "o0904"):
        assert outfits[token]["observations"]["structure"] == "pants"


def test_ornate_candidates_are_not_promoted_to_daily_basics():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0877", "o0888", "o0898", "o0900", "o0907", "o0911"):
        assert outfits[token]["status"] == "ai_candidate"
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o0868", "o0872", "o0873", "o0874", "o0881", "o0884", "o0886", "o0887", "o0891", "o0894", "o0906", "o0910"):
        assert outfits[token]["observations"]["persona_scores"]["bolt"] < 0.55
    for token in ("o0870", "o0889"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]


def test_film_series_uses_visual_structure_not_earth_color_or_catalog_name():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0912", "o0919", "o0923", "o0933"):
        scores = outfits[token]["observations"]["persona_scores"]
        assert scores["void"] >= 0.55
        assert scores["film"] < 0.55
    assert outfits["o0921"]["observations"]["persona_scores"]["film"] >= 0.55
    for token in ("o0922", "o0932"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
    for token in ("o0923", "o0933"):
        assert outfits[token]["status"] == "ai_candidate"
    for token in ("o0914", "o0927", "o0929"):
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for number in range(932, 937):
        assert outfits[f"o{number:04d}"]["observations"]["structure"] == "skirt"


def test_jade_basics_do_not_inherit_ink_accessory_persona_or_color():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for number in range(957, 977):
        assert outfits[f"o{number:04d}"]["observations"]["structure"] == "pants"
    for token in ("o0957", "o0958", "o0961", "o0964", "o0965", "o0966", "o0967", "o0968", "o0974", "o0975", "o0976", "o0979", "o0985", "o0986", "o0989", "o0995", "o0997", "o1000"):
        assert outfits[token]["observations"]["persona_scores"]["jade"] < 0.55
    for token in ("o0962", "o0970", "o0977", "o0978", "o0980", "o0982", "o0983", "o0988"):
        assert outfits[token]["observations"]["persona_scores"]["jade"] >= 0.75
    for token in ("o0959", "o0963", "o0971", "o0973"):
        assert outfits[token]["observations"]["persona_scores"]["jade"] >= 0.6
    for token in ("o0965", "o0966", "o0979", "o0985"):
        assert outfits[token]["observations"]["main_colors"] == ["ivory"]
    assert "sage" in outfits["o0981"]["observations"]["main_colors"]


def test_review_distinguishes_covered_torsos_wrap_pants_and_redundant_belts():
    result = compile_review(AUDIT)
    outfits = {r["token"]: r for r in result["outfits"].values()}
    for token in ("o0944", "o0962", "o0977", "o0980", "o0983", "o0988", "o1006"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0950", "o0991", "o0992", "o0993"):
        assert outfits[token]["status"] == "needs_review"
        assert "outer_inner_volume_unverified" in outfits[token]["observations"]["conflicts"]
    for token in ("o0949", "o0990", "o0994"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "outer_inner_volume_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o0990", "o0991", "o0992", "o0993", "o0994", "o1001", "o1007"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o0996", "o0999"):
        assert outfits[token]["status"] == "needs_review"
        assert "redundant_waist_accessory_unverified" in outfits[token]["observations"]["conflicts"]
    assert outfits["o0998"]["status"] == "ai_candidate"
    assert outfits["o1007"]["status"] == "needs_review"
    assert "multiple_focal_competition" in outfits["o1007"]["observations"]["conflicts"]
    assert outfits["o1008"]["status"] == "ai_candidate"


def test_loop_visual_evidence_distinguishes_modular_pieces_from_plain_basics():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1001", "o1002", "o1004", "o1017", "o1018", "o1020", "o1025", "o1032"):
        assert outfits[token]["observations"]["persona_scores"]["loop"] >= 0.7
    for token in ("o1009", "o1010", "o1023", "o1024", "o1034", "o1036"):
        assert outfits[token]["observations"]["persona_scores"]["loop"] < 0.4
    for token in ("o1013", "o1026", "o1035", "o1038", "o1045"):
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]


def test_noir_visual_evidence_does_not_inherit_black_or_accessory_labels():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1043", "o1045", "o1053", "o1056"):
        scores = outfits[token]["observations"]["persona_scores"]
        assert scores["edge"] > scores["noir"]
    for token in ("o1046", "o1047", "o1048", "o1055"):
        assert outfits[token]["observations"]["persona_scores"]["noir"] < 0.35
    for token in ("o1040", "o1042", "o1049", "o1052"):
        assert outfits[token]["observations"]["persona_scores"]["noir"] >= 0.75
    assert outfits["o1048"]["observations"]["main_colors"] == ["blue"]
    assert outfits["o1050"]["observations"]["main_colors"] == ["black"]


def test_modular_reviews_keep_focal_and_sleeve_issues_separate_from_coverage():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1014", "o1028", "o1044"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
    assert "outer_inner_volume_unverified" in outfits["o1031"]["observations"]["conflicts"]
    for token in ("o1026", "o1029", "o1030", "o1032", "o1033", "o1043", "o1045", "o1049", "o1056"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])
    for token in ("o1028", "o1033", "o1044", "o1045", "o1050", "o1052"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o1017", "o1025", "o1026"):
        assert outfits[token]["observations"]["structure"] == "skirt"


def test_noir_replacements_preserve_lining_and_layering_review_boundaries():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1067", "o1068"):
        assert outfits[token]["status"] == "needs_review"
        assert "opaque_inner_unverified" in outfits[token]["observations"]["conflicts"]
    assert "outer_inner_volume_unverified" in outfits["o1076"]["observations"]["conflicts"]
    assert "multiple_focal_competition" in outfits["o1073"]["observations"]["conflicts"]
    for token in ("o1065", "o1069", "o1070", "o1074", "o1075", "o1077", "o1080"):
        assert outfits[token]["status"] == "ai_candidate"
    for token in ("o1057", "o1058", "o1066", "o1069", "o1075", "o1080"):
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o1064", "o1074", "o1077", "o1078"):
        assert outfits[token]["observations"]["persona_scores"]["noir"] < 0.4


def test_void_reviews_use_actual_material_structure_not_neutral_palette():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1084", "o1086", "o1091", "o1092", "o1097", "o1100", "o1107", "o1108", "o1110", "o1111", "o1123", "o1124", "o1126", "o1127"):
        assert outfits[token]["observations"]["persona_scores"]["void"] < 0.4
    for token in ("o1087", "o1089", "o1096", "o1098", "o1099", "o1101", "o1115", "o1118", "o1125"):
        assert outfits[token]["observations"]["persona_scores"]["void"] >= 0.7
    assert outfits["o1122"]["observations"]["persona_scores"]["wabi"] > outfits["o1122"]["observations"]["persona_scores"]["void"]
    assert outfits["o1124"]["observations"]["main_colors"] == ["taupe"]
    for token in ("o1088", "o1093", "o1095", "o1102", "o1103", "o1105", "o1119"):
        assert outfits[token]["status"] == "needs_review"
        assert "multiple_focal_competition" in outfits[token]["observations"]["conflicts"]
    for token in ("o1094", "o1096", "o1098", "o1104", "o1106", "o1112"):
        assert outfits[token]["status"] == "ai_candidate"


def test_void_wrap_pants_and_experimental_records_keep_specific_evidence():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1093", "o1095", "o1116", "o1117", "o1118", "o1119", "o1120", "o1121", "o1128"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o1082", "o1114", "o1121", "o1125"):
        assert outfits[token]["status"] == "ai_candidate"
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    for token in ("o1120", "o1128"):
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    for token in ("o1089", "o1113", "o1114", "o1116", "o1118", "o1122", "o1125"):
        assert outfits[token]["status"] == "ai_candidate"
        assert "opaque_inner_unverified" not in (outfits[token]["observations"]["conflicts"] or [])


def test_full_native_review_is_not_publish_or_blind_approval():
    result = compile_review(AUDIT)
    assert result["status"] == "full_semantic_review_recorded"
    assert result["completion"]["garments"]["full_field_reviews"] == 600
    assert result["completion"]["outfits"]["full_field_reviews"] == 1169
    assert result["publish_approval"] is False
    assert result["human_reviewed"] is False
    assert result["independent_blind_review"] is False
    assert result["counts"]["outfits"]["needs_review"] > 0


def test_oops_actual_structure_and_accessory_only_persona_evidence():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1129", "o1130", "o1140", "o1145", "o1159", "o1161"):
        assert outfits[token]["observations"]["structure"] == "pants"
    for token in ("o1146", "o1147", "o1156", "o1157"):
        assert outfits[token]["observations"]["structure"] == "skirt"
    for token in ("o1132", "o1133", "o1149", "o1150", "o1152", "o1153", "o1154", "o1160", "o1164", "o1167", "o1168"):
        assert outfits[token]["observations"]["persona_scores"]["oops"] < 0.4
    for token in ("o1152", "o1153", "o1154", "o1164", "o1167", "o1168"):
        assert outfits[token]["observations"]["main_colors"] == ["blue"]
    for token in ("o1135", "o1139", "o1151", "o1155", "o1163", "o1165"):
        scores = outfits[token]["observations"]["persona_scores"]
        assert scores["neon"] > scores["oops"]


def test_oops_hold_and_experimental_boundaries_survive_replacements():
    outfits = {r["token"]: r for r in compile_review(AUDIT)["outfits"].values()}
    for token in ("o1136", "o1137", "o1157", "o1161", "o1166"):
        assert "paired_heel_balance_unverified" in outfits[token]["observations"]["conflicts"]
        assert outfits[token]["status"] != "ai_candidate"
    for token in ("o1141", "o1145", "o1146", "o1161"):
        assert outfits[token]["status"] == "suggested_exclude"
        assert "multiple_focal_overload" in outfits[token]["observations"]["conflicts"]
    for token in ("o1131", "o1134", "o1140", "o1142", "o1143", "o1144", "o1148", "o1159", "o1162", "o1163", "o1165"):
        assert outfits[token]["status"] == "ai_candidate"
        assert outfits[token]["observations"]["expression"] == "experimental"
        assert "daily" not in outfits[token]["observations"]["scenes"]
    assert "outer_inner_volume_unverified" in outfits["o1161"]["observations"]["conflicts"]
    assert "outer_inner_volume_unverified" not in (outfits["o1162"]["observations"]["conflicts"] or [])
    assert "paired_heel_balance_unverified" not in outfits["o1169"]["observations"]["conflicts"]
    assert outfits["o1169"]["status"] == "needs_review"


def test_compiler_rejects_unrecognized_persona(monkeypatch):
    monkeypatch.setattr("scripts.compile_selfit_codex_visual_review.PERSONAS", set())
    with pytest.raises(AssertionError):
        compile_review(AUDIT)


def test_compiler_rejects_unrecognized_expression(monkeypatch):
    monkeypatch.setattr("scripts.compile_selfit_codex_visual_review.EXPRESSIONS", set())
    with pytest.raises(AssertionError, match="Unknown expression"):
        compile_review(AUDIT)

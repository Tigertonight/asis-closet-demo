import json

from app.recommendation_visual import valid_observation
from scripts import compile_selfit_p0_batch18_review as review


def test_batch18_review_is_current_and_nonformal():
    result = review.build_review()
    rendered = json.loads(review.RENDERED.read_text())
    raw_by_id = {row["new_record"]["id"]: row["new_record"] for row in rendered["entries"]}
    assert len(result["entries"]) == 20
    assert result["independent_blind_review"] is False
    assert result["four_gate_editorial_review"] is False
    assert result["formal_acceptance"] is False
    for row in result["entries"]:
        raw = raw_by_id[row["outfit_id"]]
        assert valid_observation(raw, row, row["image_url"], "outfits")
        assert row["observations"]["persona_scores"][raw["primary_persona"].lower()] >= .55
        assert row["evidence_scope"].startswith("Production-side triage only")


def test_batch18_tasks_are_unique_and_complete():
    result = review.build_review()
    assert len({row["task_id"] for row in result["entries"]}) == 20
    assert all(row["observations"]["conflicts"] for row in result["entries"])


def test_review_compiler_supports_batch19_without_overwriting_batch18():
    audit = review.AUDIT
    result = review.build_review(
        audit / "gap-recipes.visual-evidence.batch19.rendered.json",
        audit / "p0-final-recipe-plan.v2.json",
        review.GARMENTS,
        sheet_dir="batch19-review",
        prompt_version="p0-final-gap-19-visual-v1",
    )
    assert result["version"].startswith("p0-final-gap-19-review-")
    assert all(row["contact_sheet"].startswith("batch19-review/") for row in result["entries"])
    assert {row["prompt_version"] for row in result["entries"]} == {"p0-final-gap-19-visual-v1"}

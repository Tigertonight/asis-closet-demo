from scripts import build_selfit_p0_case_ledger as ledger


def test_partial_ledger_reports_only_directly_proven_cases_as_pass():
    audit = ledger.ROOT / "docs/audits/20260904-p0-acceptance"
    result = ledger.build_ledger(
        audit / "anchor-candidates.v61.json",
        [audit / "final-batch19-preflight.v1.json",
         audit / "final-batch19-preflight-regression.v1.xml"],
        "2026-09-06T00:00:00+00:00",
    )
    assert result["summary"] == {"total": 94, "pass": 9, "not_run": 85, "fail": 0, "blocked": 0}
    assert {case_id for case_id, row in result["cases"].items() if row["status"] == "Pass"} == set(ledger.DIRECT_CASES)
    assert all(row["artifacts"] for row in result["cases"].values() if row["status"] == "Pass")

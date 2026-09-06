import json
from pathlib import Path

import pytest
from PIL import Image

from scripts import audit_selfit_p0_raw_garment_supply as audit
from scripts import build_selfit_p0_generated_garment_batch11 as register
from scripts import build_selfit_p0_final_recipe_batch18 as recipe_batch
from scripts import revise_selfit_p0_final_recipe_plan_v2 as revise_plan


def test_current_raw_supply_covers_exact_backlog():
    plan = audit.AUDIT_ROOT / "raw-supply-plan.v1.json"
    result = audit.inspect(plan)
    assert result["status"] == "raw_supply_complete_pending_normalization"
    assert result["summary"]["raw_garments"] == 15
    assert result["summary"]["planned_outfits"] == 20
    assert result["errors"] == []
    assert all(row["alpha_extrema"] == [0, 255] for row in result["entries"])


def test_no_alpha_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "supply"
    root.mkdir()
    Image.new("RGB", (32, 32), "white").save(root / "bad.png")
    plan = root / "plan.json"
    data = {"schema_version": 1, "entries": [
        {"token": "n0102", "persona": "oops", "slug": "bad",
         "source": "bad.png", "targets": ["easy:dress", "easy:dress"]}
    ]}
    plan.write_text(json.dumps(data))
    monkeypatch.setattr(audit, "AUDIT_ROOT", root)
    monkeypatch.setattr(audit, "TARGETS", {"oops": audit.Counter({"easy:dress": 2})})
    monkeypatch.setattr(audit, "PERSONAS", {"oops"})
    result = audit.inspect(plan)
    assert result["status"] == "raw_supply_invalid"
    assert result["entries"][0]["technical_status"] == "rejected_no_alpha"


def test_registration_specs_bind_every_raw_input_and_target():
    specs = register.specs()
    plan = json.loads(register.PLAN.read_text())["entries"]
    assert len(specs) == len(plan) == 15
    assert len({row["token"] for row in specs}) == 15
    assert {row["slug"] for row in specs} == {row["slug"] for row in plan}
    assert sum(len(row["targets"]) for row in specs) == 20
    assert all(Path(row["source_output"]).is_file() for row in specs)
    assert all(row["prompt"] for row in specs)
    assert register.verify_sources()["summary"]["planned_outfits"] == 20


def test_registration_rejects_source_fingerprint_drift(tmp_path):
    evidence = json.loads(register.RAW_AUDIT.read_text())
    evidence["entries"][0]["sha256"] = "0" * 64
    changed = tmp_path / "changed-audit.json"
    changed.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="raw source changed"):
        register.verify_sources(changed)


def test_final_recipe_plan_matches_the_twenty_backlog_tasks():
    recipe_plan = json.loads((register.ROOT / "docs/audits/20260904-p0-acceptance/p0-final-recipe-plan.v1.json").read_text())
    backlog = json.loads((register.ROOT / "docs/audits/20260904-p0-acceptance/production-backlog.v13.json").read_text())
    recipes = recipe_plan["recipes"]
    expected = {(row["task_id"], row["persona"].upper(), row["expression"], row["structure"])
                for row in backlog["tasks"]}
    actual = {(row["task_id"], row["persona"], row["expression"], row["structure"])
              for row in recipes}
    assert actual == expected
    assert len(recipes) == len({row["task_id"] for row in recipes}) == 20
    hero_use = audit.Counter((row["persona"], row["hero"]) for row in recipes)
    assert max(hero_use.values()) <= 2
    assert len({tuple(row["items"]) for row in recipes}) == 20
    for row in recipes:
        assert row["hero"] in row["items"]
        assert len(row.get("layer_graph", [])) == (1 if len([x for x in row["items"] if x in {"g0097", "g0096", "g0136"}]) > 0 and row["structure"] in {"dress", "pants"} and row["task_id"] in {"P0-CONTENT-BOLT-04", "P0-CONTENT-EDGE-04", "P0-CONTENT-NEON-07", "P0-CONTENT-OOPS-02"} else 0)


def _fake_final_manifest():
    return {"schema_version":1,"status":"internal_candidate","production_approved":False,
            "version":"fake-v1","visual":{
                f"garment-{i}":{"token":f"n{i:04d}"} for i in range(102,117)}}


def test_recipe_batch_binds_all_new_and_existing_tokens():
    plan = json.loads((register.ROOT / "docs/audits/20260904-p0-acceptance/p0-final-recipe-plan.v1.json").read_text())
    current = {"version":"visual-v1","garments":{
        token:{"token":token} for token in ["g0003","g0004","g0005","g0096","g0097","g0136","g0433"]}}
    result = recipe_batch.build_spec(plan, _fake_final_manifest(), current,
                                     manifest_ref="generated-garments/batch11/manifest.json")
    assert len(result["recipes"]) == 20
    assert result["new_garment_version"] == "fake-v1"
    assert len([row for row in result["recipes"] if row.get("layer_graph")]) == 4


def test_recipe_batch_rejects_incomplete_generated_manifest():
    plan = json.loads((register.ROOT / "docs/audits/20260904-p0-acceptance/p0-final-recipe-plan.v1.json").read_text())
    manifest = _fake_final_manifest()
    manifest["visual"].pop("garment-116")
    with pytest.raises(ValueError, match="n0102..n0116"):
        recipe_batch.build_spec(plan, manifest, {"version":"v","garments":{}}, manifest_ref="m.json")


def test_v2_recipe_plan_replaces_only_the_overused_support_items():
    original = json.loads(revise_plan.SOURCE.read_text())
    revised = revise_plan.revise(original)
    before = {row["task_id"]: row for row in original["recipes"]}
    after = {row["task_id"]: row for row in revised["recipes"]}
    changed = {task for task in before if before[task] != after[task]}
    assert changed == set(revise_plan.REPLACEMENTS)
    assert len({tuple(row["items"]) for row in revised["recipes"]}) == 20
    for task, replacements in revise_plan.REPLACEMENTS.items():
        assert not set(replacements) & set(after[task]["items"])
        assert set(replacements.values()) <= set(after[task]["items"])

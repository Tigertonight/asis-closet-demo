import copy
import json
from pathlib import Path

import pytest

from app.recommendation_aw import enabled,prepare_candidates
from app.recommendation_sequence import daily_candidates,select_flexible_sequence,VERSION
from app.recommendation_feed import create_feed,continue_feed
from app.storage import user_storage
from scripts.audit_selfit_personal_home_supply import sequence_diagnostics
from scripts.build_selfit_aw_repair_ledger import build
from tests.test_personal_home_v3 import outfit,profile

ROOT=Path(__file__).resolve().parents[1]


def test_aw_context_does_not_invent_weather_or_change_other_scenes(monkeypatch):
    from app.recommendation_aw import validation_context
    monkeypatch.delenv("SELFIT_RECOMMENDATION_AW_SEASON", raising=False)
    assert validation_context({}, {}) is None
    monkeypatch.setenv("SELFIT_RECOMMENDATION_AW_SEASON", "autumn")
    original = {}
    assert validation_context(original, {})["season_source"] == "internal_validation_configuration"
    assert original == {}
    for season in ("unknown", "summer", ["autumn", "winter"]):
        assert validation_context({"season_tags":season}, {}) is None
    assert validation_context({"scene_tags":"formal"}, {}) is None
    assert validation_context({"season_tags":"冬季"}, {})["season_tags"] == "冬季"


def test_repair_references_are_replaced_without_mutating_source():
    from scripts.render_selfit_aw_repairs import replace_ids
    source = {"garment_ids":["old"], "slot_roles":{"old":"support"}, "layer_graph":[{"inner":"old"}]}
    before = copy.deepcopy(source)
    changed = replace_ids(source, {"old":"new"})
    assert source == before
    assert changed == {"garment_ids":["new"], "slot_roles":{"new":"support"}, "layer_graph":[{"inner":"new"}]}


def test_rendered_repair_drafts_do_not_inherit_approval():
    from app.recommendation_visual import asset_sha
    from app.selfit_content_quality import record_fingerprint
    data=json.loads((ROOT/"docs/audits/20260904-aw-supply/repairs.batch01.rendered.json").read_text())
    assert len(data["entries"]) == 3
    for entry in data["entries"]:
        row=entry["new_record"]
        assert row["id"] != entry["source_outfit_id"]
        assert row["annotation"]["status"] == "draft" and entry["review"] is None
        assert "quality_review" not in row and "curation" not in row
        assert record_fingerprint(row) == entry["record_fingerprint"]
        assert asset_sha(row["assets"]["image_url"]) == entry["asset_sha256"]


def test_recomposition_loader_admits_only_bound_candidates():
    from app.closet import selfit_content_pool
    from app.recommendation_aw import load_recomposition_candidates
    from app.recommendation_visual import load_visual
    pool=selfit_content_pool()
    rows,version=load_recomposition_candidates(pool.garments,load_visual())
    assert len(rows)==488 and version=="aw-recomposition-index-20260904-25"
    assert all(row["source"]=="aw_reviewed_draft" and row["visual"]["seasons"] in (["autumn"],["winter"]) for row in rows)
    assert sum(row["visual"]["seasons"]==["winter"] for row in rows)==284
    assert {row["outfit_id"] for row in rows}.isdisjoint({o["id"] for o in pool.outfits})
    assert {"outfit_mute_aw-recompose-01_15","outfit_melt_aw-recompose-01_18"}.isdisjoint({r["outfit_id"] for r in rows})
    assert {"outfit_mute_aw-recompose-02_01","outfit_melt_aw-recompose-02_02"} <= {r["outfit_id"] for r in rows}
    assert {"outfit_oops_master_06_v1__aw-repair-02","outfit_oops_master_06_v2__aw-repair-02"} <= {r["outfit_id"] for r in rows}
    generated = [row for row in rows if row["outfit_id"].startswith("outfit_") and "aw-winter-02" in row["outfit_id"]]
    assert len(generated) == 9
    assert all(any(item.get("outfit_role") == "hero" for item in row["items"]) for row in generated)


def test_generated_gap_fill_garments_are_immutable_internal_candidates():
    from app.recommendation_visual import asset_sha,valid_observation
    pool=json.loads((ROOT/"app/static/selfit/data/content-pool.v2.published.json").read_text())
    seen=set()
    for batch in ("batch01","batch02","batch03","batch04","batch06","batch07","batch08","batch09","batch10","batch11","batch12","batch13"):
        manifest=json.loads((ROOT/f"docs/audits/20260904-aw-supply/generated-garments/{batch}/manifest.json").read_text())
        expected_count={"batch01":4,"batch02":4,"batch03":8,"batch04":1,"batch06":8,"batch07":8,"batch08":6,"batch09":8,"batch10":8,"batch11":8,"batch12":8,"batch13":8}[batch]
        assert manifest["production_approved"] is False and len(manifest["garments"])==expected_count
        assert {g["id"] for g in manifest["garments"]}.isdisjoint({g["id"] for g in pool["garments"]}|seen)
        seen|={g["id"] for g in manifest["garments"]}
        for garment in manifest["garments"]:
            observation=manifest["visual"][garment["id"]]
            assert garment["production"]["source_kind"]=="generated_original"
            assert garment["production"]["reference_ids"]==[]
            assert garment["assets"]["rights_status"]=="owned"
            assert asset_sha(garment["assets"]["image_url"])==garment["color_evidence"]["asset_sha256"]
            assert valid_observation(garment,observation,garment["assets"]["image_url"],"garments")


def test_concurrent_generation_manifest_with_wrong_content_binding_is_quarantined():
    root=ROOT/"docs/audits/20260904-aw-supply"
    disposition=json.loads((root/"generated-garments/batch05/review-disposition.json").read_text())
    index=json.loads((root/"recomposition-index.json").read_text())
    assert disposition["status"]=="rejected_manifest" and disposition["production_approved"] is False
    assert "generated-garments/batch05/manifest.json" not in {row.get("garment_manifest") for row in index["batches"]}
    assert "generated-garments/batch06/manifest.json" in {row.get("garment_manifest") for row in index["batches"]}


def rows(count=60,expression="typical"):
    result=[outfit(i,category=("pants","skirt","dress")[i%3],expression=expression) for i in range(count)]
    for r in result:r["visual"]["wearability"]="everyday_with_statement"
    return result


def test_typical_daily_can_fill_without_fixed_easy_slot():
    data=rows()
    selected,gaps,meta=select_flexible_sequence(data)
    assert len(selected)==30 and not gaps
    assert set(meta["first_ten_structures"])=={"pants","skirt","dress"}
    assert max(meta["first_ten_structures"].values())<=5
    assert meta["expression_distribution"]["carousel"]=={"typical":4}
    assert not sequence_diagnostics(selected)["constraint_violations"]
    assert select_flexible_sequence(data)[0]==selected


def test_unknown_daily_and_experiment_cannot_fill():
    data=rows(4)
    data[0]["visual"]["wearability"]=None
    data[1]["visual"]["expression"]="experimental"
    data[2]["visual"]["wearability"]="occasion_only"
    accepted,rejected=daily_candidates(data)
    assert accepted==[data[3]] and rejected=={"daily_wearability_unconfirmed":3}


def test_winter_requires_explicit_full_layers_evidence():
    data=rows(2)
    data[0]["visual"]["winter_outdoor"]="complete_layers_visually_reviewed"
    accepted,rejected=daily_candidates(data,winter=True)
    assert accepted==[data[0]] and rejected=={"winter_outdoor_unconfirmed":1}


def test_repeated_main_and_family_never_relaxed_to_fill():
    data=rows()
    for r in data:r["items"][0]["style_family_id"]="same-family"
    selected,gaps,_=select_flexible_sequence(data)
    assert len(selected)==2 and gaps and not gaps[0]["exhaustive_infeasibility_proven"]
    assert not sequence_diagnostics(selected)["constraint_violations"]


def test_parent_separation_and_lower_ranked_structure():
    data=rows(90)
    for i,r in enumerate(data):r["parent_outfit_id"]=f"parent-{i//3}"
    data.sort(key=lambda r:r["visual"]["structure"]!="pants")
    selected,_,_=select_flexible_sequence(data)
    assert len(selected)==30 and not sequence_diagnostics(selected)["constraint_violations"]


def test_scarce_structure_is_selected_before_rolling_constraints_close():
    data=rows(17)
    for i,r in enumerate(data):
        r["visual"]["structure"] = "pants" if i < 12 else "dress" if i < 16 else "skirt"
        r["recommendation"] = {"score": 100-i}
    selected,gaps,meta=select_flexible_sequence(data,limit=10)
    assert len(selected)==10 and not gaps
    assert set(meta["first_ten_structures"])=={"pants","skirt","dress"}


def test_short_and_category_filtered_supply_reports_truth():
    data=rows(40)
    for r in data:r["visual"]["structure"]="pants"
    selected,gaps,_=select_flexible_sequence(data)
    assert len(selected)<=5 and gaps[0]["reason"]=="missing_main_structure"
    selected,gaps,_=select_flexible_sequence(data,category_filtered=True)
    assert len(selected)==30 and not gaps


def test_aw_needs_both_switch_and_exact_allowlist(monkeypatch):
    monkeypatch.setenv("SELFIT_RECOMMENDATION_AW_ENABLED","1")
    monkeypatch.setenv("SELFIT_RECOMMENDATION_V3_ENABLED","1")
    monkeypatch.setenv("SELFIT_RECOMMENDATION_V3_USERS","internal")
    assert enabled("internal") and not enabled("other")
    monkeypatch.setenv("SELFIT_RECOMMENDATION_AW_ENABLED","0")
    assert not enabled("internal")


def test_draft_mapping_is_copied_revision_bound_and_does_not_promote():
    from app.closet import selfit_content_pool,_published_catalog_outfits
    from app.recommendation_visual import load_visual,attach_visual
    pool=selfit_content_pool();v=load_visual()
    candidates,_=attach_visual(_published_catalog_outfits(),pool.garments,pool.outfits,v)
    original=copy.deepcopy(candidates)
    prepared,bundle=prepare_candidates(candidates,pool.garments,v)
    assert candidates==original and bundle["strategy"]==VERSION
    assert len(prepared)==len(candidates)
    assert any(i["style_family_id"].startswith("native:") for o in prepared for i in o["items"])
    with pytest.raises(ValueError,match="Stale family"):
        prepare_candidates(candidates,pool.garments,{**v,"version":"changed"})


def test_snapshot_keeps_strategy_and_order_on_continuation(tmp_path,monkeypatch):
    import app.storage as storage
    monkeypatch.setattr(storage,"ROOT_DIR",tmp_path)
    bundle={"strategy":VERSION,"visual":"v1","families":"f1","content":"c1"}
    with user_storage("aw-test"):
        first=create_feed(profile(),rows(),{},validation_bundle=bundle)
        assert first["algorithm"]==VERSION and len(first["carousel"])+len(first["outfits"])==10
        second=continue_feed(first["session_id"],first["next_cursor"],profile())
        assert second["validation_bundle"]==bundle and second["algorithm"]==VERSION
        assert not {r["outfit_id"] for r in first["carousel"]+first["outfits"]}&{r["outfit_id"] for r in second["outfits"]}


def test_ledger_covers_all_without_fabricating_repairs():
    read=lambda p:json.loads(p.read_text())
    audit=ROOT/"docs/audits/20260903-personal-home-visual"
    data=build(read(audit/"full-native-audit-summary.json"),read(ROOT/"app/data/recommendation-visual.v1.json"),
               read(ROOT/"app/static/selfit/data/content-pool.v2.published.json"))
    assert data["counts"]=={"focal_cohesion":83,"opaque_coverage":47,"layer_structure":52,"season_scene":19,"paired_shoes":16}
    assert len(data["entries"])==217 and len(data["unused_main_garments"])==35
    assert all(r["review_decision"] is None and r["new_revision_id"] is None for r in data["entries"])
    assert sum(r["disposition"]=="exit_default_recommendation" for r in data["entries"])==33


def test_all_217_findings_have_one_evidence_bound_disposition():
    root=ROOT/"docs/audits/20260904-aw-supply"
    files={
        "paired-shoes.dispositions.json":16,
        "season-scene.dispositions.json":19,
        "opaque-coverage.dispositions.json":47,
        "layer-structure.dispositions.json":52,
        "focal-cohesion.dispositions.json":83,
    }
    tokens=[]
    for filename,expected in files.items():
        data=json.loads((root/filename).read_text())
        assert len(data["entries"])==expected==sum(data["counts"].values())
        assert all(row["original_preserved"] for row in data["entries"])
        assert not data.get("production_approved",False)
        tokens.extend(row["token"] for row in data["entries"])
    assert len(tokens)==217 and len(set(tokens))==217

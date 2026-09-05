"""Build an immutable-source repair worklist; proposed actions are not approvals."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_profile import digest

AUDIT = ROOT / "docs/audits/20260903-personal-home-visual"
OUTPUT = ROOT / "docs/audits/20260904-aw-supply"
POLICIES = {
    "opaque_coverage": ("内搭覆盖", "指定真实不透内搭或衬裙；无法核实则替换透感主衣", "成套图可核实必要内层、覆盖与层级"),
    "paired_shoes": ("成对鞋平衡", "优先换用已审核且左右结构协调的鞋，异常原鞋保持待核", "成对鞋结构、视觉跟高与全套风格协调；实物舒适性未知"),
    "layer_structure": ("叠穿结构", "简化内层袖量、重复门襟和腰部装饰；必要时换外层", "袖量、肩线、衣长和腰部关系清楚，不依靠遮挡藏问题"),
    "season_scene": ("季节场景", "先判断是否调整用途；需要秋冬日常版本时实质更换外层/下装/鞋", "整套场景一致，冬季外出须单独审核，不机械添加季节标签"),
    "focal_cohesion": ("主次与风格", "保留一个有该人格证据的主视觉，简化竞争的主衣或配件", "人格来自主服装及结构，主次明确，不依赖夸张鞋包"),
}


def primary_group(row):
    conflicts = " ".join(row["conflicts"])
    held = " ".join(row["held_garment_ids"])
    if "opaque" in conflicts or any(t in held for t in ("0354", "0343", "0359", "0425", "0567")):
        return "opaque_coverage"
    if "paired_heel" in conflicts or "0080" in held:
        return "paired_shoes"
    if any(t in conflicts for t in ("volume", "shoulder_fit", "waist_styling", "waist_accessory")) or "0573" in held:
        return "layer_structure"
    if any(t in conflicts for t in ("season", "occasion", "formality", "costume")):
        return "season_scene"
    return "focal_cohesion"


def build(summary, visual, pool):
    assert summary["visual_version"] == visual["version"]
    raw = {o["id"]: o for o in pool["outfits"]}
    result = []
    for row in summary["problem_outfits"]:
        group = primary_group(row)
        observation = visual["outfits"][row["outfit_id"]]
        result.append({"repair_id": "aw-repair:"+row["outfit_id"], "outfit_id":row["outfit_id"],
            "token":row["token"], "original_status":row["status"], "primary_group":group,
            "all_conflicts":row["conflicts"], "held_garment_ids":row["held_garment_ids"],
            "source_visual_version":visual["version"], "source_record_fingerprint":observation["record_fingerprint"],
            "source_asset_sha256":observation["asset_sha256"], "source_image_url":observation["image_url"],
            "source_garment_ids":raw[row["outfit_id"]]["garment_ids"], "source_parent_recipe":row["parent_recipe"],
            "design_intent_to_preserve":row["evidence"], "problem_evidence":row["visual_evidence"],
            "proposed_action":POLICIES[group][1], "recheck_criterion":POLICIES[group][2],
            "target_conditions":{"personas":sorted(p for p,s in row["visual_scores"].items() if s>=.55),
                                 "seasons":["autumn","winter"],"scene":"daily","status":"design_targets_not_approved_suitability"},
            "workflow_status":"needs_designed_revision", "disposition":"exit_default_recommendation" if row["status"]=="suggested_exclude" else "retain_pending_review",
            "replacement_garments":[], "added_garments":[], "new_revision_id":None,
            "review_decision":None, "unresolved_issues":row["conflicts"] or ["linked_garment_review"],
            "original_preserved":True})
    assert len({r["outfit_id"] for r in result})==len(result)==217
    return {"schema_version":1,"version":"aw-repairs-"+digest(result)[:20],
        "source_visual_version":visual["version"],"status":"repair_worklist_not_repaired",
        "counts":dict(Counter(r["primary_group"] for r in result)),"entries":result,
        "unused_main_garments":[r for r in summary["unused_garments"] if r["category"] in {"top","outer","bottom","skirt","dress"}],
        "production_approved":False}


def main():
    read=lambda p:json.loads(p.read_text())
    data=build(read(AUDIT/"full-native-audit-summary.json"),read(ROOT/"app/data/recommendation-visual.v1.json"),
               read(ROOT/"app/static/selfit/data/content-pool.v2.published.json"))
    OUTPUT.mkdir(parents=True,exist_ok=True)
    path=OUTPUT/"repair-ledger.initial.json"
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+"\n"
    if path.exists() and path.read_text()!=serialized:
        raise SystemExit("Initial ledger exists; write a new revision rather than overwrite work")
    path.write_text(serialized)
    print(json.dumps({"version":data["version"],"counts":data["counts"],"unused_main":len(data["unused_main_garments"])},ensure_ascii=False))


if __name__=="__main__":main()

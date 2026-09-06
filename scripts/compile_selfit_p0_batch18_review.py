#!/usr/bin/env python3
"""Compile a current-session, non-blind whole-image judgment for a P0 batch."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_visual import load_visual


AUDIT = ROOT / "docs/audits/20260904-p0-acceptance"
RENDERED = AUDIT / "gap-recipes.visual-evidence.batch18.rendered.json"
PLAN = AUDIT / "p0-final-recipe-plan.v1.json"
GARMENTS = AUDIT / "generated-garments/batch11/manifest.json"
OUTPUT = AUDIT / "gap-recipes.visual-evidence.batch18.visual-review.json"

SCORES = {
    "P0-CONTENT-BOLT-01": .62, "P0-CONTENT-BOLT-02": .78,
    "P0-CONTENT-BOLT-03": .76, "P0-CONTENT-BOLT-04": .80,
    "P0-CONTENT-EDGE-01": .72, "P0-CONTENT-EDGE-02": .70,
    "P0-CONTENT-EDGE-03": .79, "P0-CONTENT-EDGE-04": .78,
    "P0-CONTENT-NEON-01": .82, "P0-CONTENT-NEON-02": .80,
    "P0-CONTENT-NEON-03": .82, "P0-CONTENT-NEON-04": .88,
    "P0-CONTENT-NEON-05": .86, "P0-CONTENT-NEON-06": .90,
    "P0-CONTENT-NEON-07": .88, "P0-CONTENT-NOIR-01": .80,
    "P0-CONTENT-OOPS-01": .82, "P0-CONTENT-OOPS-02": .76,
    "P0-CONTENT-VOID-01": .64, "P0-CONTENT-VOID-02": .60,
}
RISKS = {
    "P0-CONTENT-BOLT-01": "低强度边界接近HEIR，须确认珠扣与滚边仍能辨识BOLT。",
    "P0-CONTENT-BOLT-02": "短摆与直裙腰部衔接、坐姿余量待实穿确认。",
    "P0-CONTENT-BOLT-03": "绿缎裹片裙可能偏晚宴，日常探索场景边界待四门复核。",
    "P0-CONTENT-BOLT-04": "花瓣外套与内搭领口、扣合及腰部余量待实穿确认。",
    "P0-CONTENT-EDGE-01": "合体针织舒适度与斜拉链末端开口待确认。",
    "P0-CONTENT-EDGE-02": "与裤装版共享上衣，需确认灰裙没有把甜酷信号稀释。",
    "P0-CONTENT-EDGE-03": "粉褶裙片行走开合与丹宁重量待确认。",
    "P0-CONTENT-EDGE-04": "粉纱视觉透明，虽有不透明内搭，覆盖与叠穿摩擦待确认。",
    "P0-CONTENT-NEON-01": "高彩上衣与黑裤关系清楚，真实面料色牢度不在平铺证据内。",
    "P0-CONTENT-NEON-02": "灰裙降低强度，仍需复核easy层级与上衣长度比例。",
    "P0-CONTENT-NEON-03": "短袖季节范围和大口袋实际容量待确认。",
    "P0-CONTENT-NEON-04": "大图形为唯一主角，袖部连续图形在实穿弯曲时待观察。",
    "P0-CONTENT-NEON-05": "与裤装版共享上衣，直裙不能造成腰线遮挡。",
    "P0-CONTENT-NEON-06": "探索强度明确，艺术活动之外的日常场景边界待复核。",
    "P0-CONTENT-NEON-07": "外搭色块强，内搭领口和斜襟闭合方式待确认。",
    "P0-CONTENT-NOIR-01": "黑色不是归类依据；覆片开口、拉链触感和行走余量待确认。",
    "P0-CONTENT-OOPS-01": "运动与西装结构冲突清楚，斜腰接缝舒适性待确认。",
    "P0-CONTENT-OOPS-02": "白色外层必须敞开，避免遮住斜腰缝和褶裙主证据。",
    "P0-CONTENT-VOID-01": "与MUTE/WABI相邻，偏缝和低口袋的可辨识度须盲审验证。",
    "P0-CONTENT-VOID-02": "白衬衫衣摆可能遮挡偏缝与口袋，需实穿调整并二审边界。",
}


def build_review(
    rendered_path: Path = RENDERED,
    plan_path: Path = PLAN,
    garments_path: Path = GARMENTS,
    *,
    sheet_dir: str = "batch18-review",
    prompt_version: str = "p0-final-gap-18-visual-v1",
) -> dict:
    rendered = json.loads(rendered_path.read_text())
    plan = json.loads(plan_path.read_text())
    generated = json.loads(garments_path.read_text())
    base = load_visual()
    visuals = {**base["garments"], **generated["visual"]}
    if len(rendered["entries"]) != 20 or len(plan["recipes"]) != 20:
        raise ValueError("rendered batch and plan must both contain 20 rows")
    entries = []
    for position, (row, target) in enumerate(zip(rendered["entries"], plan["recipes"]), 1):
        raw = row["new_record"]
        if raw["primary_persona"] != target["persona"] or row["hero"] != target["hero"]:
            raise ValueError("render order no longer matches the reviewed plan")
        hero_id = next(gid for gid in raw["garment_ids"] if visuals[gid]["token"] == target["hero"])
        hero_observation = visuals[hero_id]["observations"]
        colors = list(dict.fromkeys(
            color for gid in raw["garment_ids"]
            if visuals[gid]["observations"]["category"] not in {"shoes", "bag"}
            for color in visuals[gid]["observations"].get("main_colors", [])))
        evidence = f"已查看实际整套图。{target['intent']} {RISKS[target['task_id']]}"
        observations = {
            "axes": {},
            "expression": target["expression"],
            "formality": "smart_casual" if target["persona"] in {"BOLT", "EDGE", "NOIR"} else "casual",
            "layering": 2 if target.get("layer_graph") else 1,
            "persona_scores": {target["persona"].lower(): SCORES[target["task_id"]]},
            "scenes": ["daily"],
            "seasons": ["autumn"],
            "structure": target["structure"],
            "wearability": "everyday" if target["expression"] == "easy" else "everyday_with_statement",
            "main_visual_slots": [hero_observation["category"]],
            "main_colors": colors,
            "conflicts": RISKS[target["task_id"]],
            "persona_evidence": evidence,
        }
        entries.append({
            "outfit_id": raw["id"], "task_id": target["task_id"], "status": "ai_candidate",
            "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
            "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
            "model": "current_codex_session", "prompt_version": prompt_version,
            "review_level": "individual_whole_image_and_contact_sheet_judgment",
            "evidence_scope": "Production-side triage only; not four-gate approval or independent blind review",
            "evidence": evidence, "confidence": .78, "review_complete": True,
            "contact_sheet": f"{sheet_dir}/recipes-{(position - 1) // 6 + 1}.jpg",
            "observations": observations,
        })
    result = {
        "schema_version": 1, "source_rendered_version": rendered["version"],
        "independent_blind_review": False, "four_gate_editorial_review": False,
        "formal_acceptance": False, "entries": entries,
    }
    version_prefix = prompt_version.removesuffix("-visual-v1") + "-review-"
    result["version"] = version_prefix + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", type=Path, default=RENDERED)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--garments", type=Path, default=GARMENTS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--sheet-dir", default="batch18-review")
    parser.add_argument("--prompt-version", default="p0-final-gap-18-visual-v1")
    args = parser.parse_args()
    result = build_review(
        args.rendered,
        args.plan,
        args.garments,
        sheet_dir=args.sheet_dir,
        prompt_version=args.prompt_version,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output.exists() and args.output.read_text() != payload:
        raise SystemExit("review changed; refusing overwrite")
    args.output.write_text(payload)
    print(json.dumps({"version":result["version"],"candidates":len(result["entries"]),
                      "four_gate":False,"blind":False},ensure_ascii=False))


if __name__ == "__main__":
    main()

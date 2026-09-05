#!/usr/bin/env python3
"""Recompose bright generated coats into restrained daily recipes."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
RECIPES = [
    ("NEON", "bright", "pants", "n0005", ["n0005", "g0108", "g0003", "g0043", "g0070"], "品红短外套作唯一高彩块，白衬衫与黑长裤建立可日常复用的对比。"),
    ("NEON", "jewel", "skirt", "n0005", ["n0005", "g0337", "g0188", "g0254", "g0513"], "鲜品红短外套与黑针织、浅色斜裹长裙构成一处高彩及短长反差。"),
    ("NEON", "bright", "dress", "n0005", ["n0005", "g0222", "g0265", "g0513"], "品红短外套叠在素色长衬衫裙上，保留鲜明比例而不使用戏剧内层。"),
    ("NOIR", "bright", "pants", "n0003", ["n0003", "g0337", "g0068", "g0069", "g0070"], "钴蓝长外套的强肩长线与全黑内搭形成锐利边界，色彩鲜明但结构不消失。"),
    ("NOIR", "bright", "skirt", "n0003", ["n0003", "g0350", "g0446", "g0069", "g0070"], "钴蓝长外套与黑色短上身、锐利直裙形成稳定短长边界，鞋包不分散焦点。"),
    ("NOIR", "bright", "dress", "n0003", ["n0003", "g0222", "g0069", "g0070"], "钴蓝强线外套覆盖灰色长衬衫裙，用黑色长靴和包延续边界。"),
    ("OOPS", "bright", "pants", "n0005", ["n0005", "g0096", "g0398", "g0505", "g0526"], "错位门襟短外套与一处角度长裤共享线条，白衬衫作稳定支撑。"),
    ("OOPS", "bright", "skirt", "n0005", ["n0005", "g0337", "g0188", "g0505", "g0513"], "错位短外套和斜裹长裙使用一个可解释的斜线母题，其余单品保持简单。"),
    ("OOPS", "bright", "dress", "n0005", ["n0005", "g0222", "g0505", "g0513"], "鲜色错位短外套与长衬衫裙形成明确短长反差，不再叠加解构长裙。"),
    ("VOID", "bright", "pants", "n0004", ["n0004", "g0337", "g0415", "g0591", "g0526"], "珊瑚红茧形长外层建立包裹感，黑针织与一处错层长裤保留低负担日常表达。"),
    ("VOID", "bright", "skirt", "n0004", ["n0004", "g0337", "g0449", "g0591", "g0526"], "茧形长外层与安静错层长裙构成一处包裹层次，运动鞋降低负担。"),
    ("VOID", "bright", "dress", "n0004", ["n0004", "g0222", "g0591", "g0526"], "珊瑚红茧形外套覆盖素色长衬衫裙，以包裹轮廓而非破片堆叠表达 VOID。"),
]


def main() -> None:
    manifest = json.loads((AUDIT / "generated-garments/combined-manifest.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = [{"persona": p, "palette": pal, "season": "winter", "structure": s, "hero": h,
                "items": items, "expression": "entry", "intent": intent}
               for p, pal, s, h, items, intent in RECIPES]
    result = {"schema_version": 1, "batch_id": "aw-winter-04", "source_visual_version": visual["version"],
              "status": "designer_targets_pending_whole_image_review", "new_garments": manifest["garments"],
              "new_garment_manifest": "generated-garments/combined-manifest.json",
              "new_garment_version": manifest["version"], "recipes": recipes}
    target = AUDIT / "winter-recipes.batch04.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": 0, "reused_generated_garments": len(manifest["garments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()

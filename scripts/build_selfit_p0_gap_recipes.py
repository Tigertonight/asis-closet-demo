"""Define four bounded P0 gap-fill recipes without publishing them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-p0-acceptance"

RECIPES = [
    {
        "persona": "FILM", "palette": "earth", "season": "autumn", "structure": "pants",
        "hero": "g0367", "items": ["g0367", "g0171", "g0266", "g0283"], "expression": "explore",
        "intent": "FILM 轻探索：把手作边缘感集中在上衣，用低腰宽裤与素色鞋包收敛，保留日常可穿性。",
    },
    {
        "persona": "ICED", "palette": "ocean", "season": "autumn", "structure": "skirt",
        "hero": "g0562", "items": ["g0562", "g0433", "g0258", "g0290"], "expression": "explore",
        "intent": "ICED 轻探索：斜向结构背心作唯一主视觉，窄长裙和低跟乐福鞋维持冷静纵向线条。",
    },
    {
        "persona": "WABI", "palette": "earth", "season": "autumn", "structure": "pants",
        "hero": "g0367", "items": ["g0367", "g0182", "g0244", "g0284"], "expression": "explore",
        "intent": "WABI 轻探索裤装：不对称针织上衣承担肌理焦点，九分锥形裤与素色配件留出呼吸感。",
    },
    {
        "persona": "WABI", "palette": "earth", "season": "autumn", "structure": "dress",
        "hero": "g0470", "items": ["g0470", "g0244", "g0283"], "expression": "explore",
        "intent": "WABI 轻探索连衣装：曲线层片只集中在主裙，鞋包保持低装饰和中性棕色，避免多焦点。",
    },
]

REPAIRS = [
    {
        "persona": "FILM", "palette": "earth", "season": "autumn", "structure": "pants",
        "hero": "g0053", "items": ["g0053", "g0171", "g0266", "g0283"], "expression": "explore",
        "intent": "FILM 轻探索修复：做旧牛仔束腰上衣是唯一复古焦点，低腰宽裤与素色鞋包支撑日常可穿性。",
    },
    {
        "persona": "WABI", "palette": "earth", "season": "autumn", "structure": "skirt",
        "hero": "g0566", "items": ["g0566", "g0433", "g0244", "g0284"], "expression": "explore",
        "intent": "WABI 轻探索修复：亚麻质感不对称上衣承担主视觉，素色窄长裙、低跟鞋和低饱和包收敛。",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true", help="build the second-pass FILM/WABI repair batch")
    args = parser.parse_args()
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    batch_id = "p0-gap-02" if args.repair else "p0-gap-01"
    recipes = REPAIRS if args.repair else RECIPES
    result = {
        "schema_version": 1,
        "batch_id": batch_id,
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": [],
        "recipes": recipes,
    }
    target = AUDIT / ("gap-recipes.batch02.json" if args.repair else "gap-recipes.batch01.json")
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("P0 gap recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "status": result["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

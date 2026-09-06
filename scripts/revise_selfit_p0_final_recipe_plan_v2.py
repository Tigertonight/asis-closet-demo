#!/usr/bin/env python3
"""Replace overused support garments found by the batch18 full-set preflight."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-p0-acceptance"
SOURCE = AUDIT / "p0-final-recipe-plan.v1.json"
OUTPUT = AUDIT / "p0-final-recipe-plan.v2.json"
REPLACEMENTS = {
    "P0-CONTENT-BOLT-01": {"g0003": "g0417"},
    "P0-CONTENT-BOLT-04": {"g0097": "g0337", "g0003": "g0178"},
    "P0-CONTENT-EDGE-04": {"g0003": "g0417"},
    "P0-CONTENT-NEON-07": {"g0003": "g0417"},
}
INTENT = {
    "P0-CONTENT-BOLT-01": "象牙丝缎上衣以酒红细滚边、三枚珠扣和轻收腰作为低强度精致焦点，炭灰压褶阔腿裤与素鞋包支撑。",
    "P0-CONTENT-BOLT-04": "酒红花瓣叠领外套以弧线珠扣和强收腰集中戏剧焦点，炭灰圆领针织提供覆盖，蓝灰直筒裤与鞋包支撑。",
    "P0-CONTENT-EDGE-04": "洗黑短外套和单侧粉纱片构成探索型甜酷主角，素内搭保障覆盖，炭灰压褶裤与鞋包控制焦点；粉纱透明度待审。",
    "P0-CONTENT-NEON-07": "橙红外搭的荧光斜襟和成对紫袋构成主动吸睛主角，素内搭与炭灰压褶裤、鞋包提供结构支撑。",
}


def revise(plan: dict) -> dict:
    result = json.loads(json.dumps(plan))
    result["status"] = "planned_after_full_set_repetition_preflight"
    seen = set()
    for row in result["recipes"]:
        changes = REPLACEMENTS.get(row["task_id"])
        if not changes:
            continue
        seen.add(row["task_id"])
        row["items"] = [changes.get(token, token) for token in row["items"]]
        for edge in row.get("layer_graph", []):
            edge["inner"] = changes.get(edge["inner"], edge["inner"])
            edge["outer"] = changes.get(edge["outer"], edge["outer"])
        row["intent"] = INTENT[row["task_id"]]
    if seen != set(REPLACEMENTS):
        raise ValueError("replacement tasks do not match plan")
    return result


def main() -> None:
    result = revise(json.loads(SOURCE.read_text()))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text() != payload:
        raise SystemExit("v2 plan changed; refusing overwrite")
    OUTPUT.write_text(payload)
    print(json.dumps({"recipes":len(result["recipes"]),"revised_tasks":len(REPLACEMENTS)},ensure_ascii=False))


if __name__ == "__main__":
    main()

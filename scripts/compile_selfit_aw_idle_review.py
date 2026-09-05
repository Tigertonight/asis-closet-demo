"""Compile the native review of the 35 unused main garments.

The decisions below were made from the three immutable sheets in idle-main-review.
They describe reuse potential; they do not approve any outfit or season claim.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

DECISIONS = {
    "g0021": ("direct_autumn_recompose", "短柔绒开衫完整；宜配简洁高腰裤或素长裙，避免再加蝴蝶结。"),
    "g0023": ("autumn_with_coverage", "短针织裙完整但长度短；秋季须有不透覆盖方案，不能直接证明冬季户外。"),
    "g0033": ("adjust_use_or_layer", "细吊带垂领花卉长裙完整，优先暖季社交；秋季须加入不透内层和外层后看图。"),
    "g0036": ("statement_not_default_daily", "高彩巨袖短夹克完整；仅适合 NEON/OOPS 鲜明表达，必须配低装饰主支撑款。"),
    "g0048": ("occasion_only", "束腰、巨泡袖、刺绣与多层裙摆同时出现，属于戏剧场合款而非默认日常。"),
    "g0051": ("direct_autumn_recompose", "复古工作服短夹克完整，适合直筒裤、锥裤或简洁裙装。"),
    "g0057": ("direct_autumn_recompose", "交领暗花外套完整；应搭无装饰内层和素下装，避免整套传统服装化。"),
    "g0066": ("direct_autumn_recompose", "黑色长皮感风衣完整，强肩长线清楚；日常版需内搭和鞋包克制。"),
    "g0369": ("direct_autumn_recompose", "炭灰素开衫完整，是可复用基础外层；与相似素开衫受家族重复约束。"),
    "g0372": ("direct_autumn_recompose", "奶白棕领短夹克完整，袋型和抽绳提供休闲焦点，宜配简洁裤裙。"),
    "g0375": ("requires_opaque_inner", "花纱罩衫完整但视觉透感明确；只有配不透内搭后才能进入秋季配方。"),
    "g0378": ("occasion_only", "花饰肩片、巨泡袖和繁复袖口同时存在，限 BOLT 场合表达。"),
    "g0381": ("direct_autumn_recompose", "宽松针织外层完整；内搭须简洁且需核对袖量，不再叠窄袖外套。"),
    "g0384": ("statement_not_default_daily", "左右不对称西装/丹宁/蕾丝外套完整但密度高；仅配素下装。"),
    "g0387": ("direct_autumn_recompose", "藏蓝奶油边圆领开衫完整，规整短比例适合 HEIR/LOOP 日常。"),
    "g0390": ("direct_autumn_recompose", "灰褐错位茧型外层完整；下装和鞋应保持单色、低装饰。"),
    "g0393": ("statement_not_default_daily", "短身、带扣、绑带和甜软花边集中在袖部；只作 EDGE 鲜明表达。"),
    "g0396": ("statement_not_default_daily", "交叠收腰和墨枝成立，但袖摆体积与装饰较高；不作极简日常外层。"),
    "g0437": ("direct_autumn_recompose", "奶油粉长层裙完整，主裙已带荷叶和蕾丝，必须配素上衣。"),
    "g0449": ("direct_autumn_recompose", "炭灰长裹片层裙完整，克制纵向层次可服务 MUTE/VOID/LOOP。"),
    "g0452": ("direct_autumn_recompose", "米色斜接褶长裙完整，低负担流动感适合 EASE/WABI/FLOU。"),
    "g0456": ("statement_not_default_daily", "高彩网面不对称衬衫裙完整，限 NEON/OOPS 典型或探索，不作默认易穿。"),
    "g0459": ("direct_autumn_recompose", "棕蓝橄榄纵拼收腰长裙完整，可用简洁短外套建立 FILM 秋季比例。"),
    "g0462": ("direct_autumn_recompose", "黑色长袖收腰衬衫裙完整，强肩与长直线足以支持 NOIR。"),
    "g0465": ("direct_autumn_recompose", "炭灰直筒中长裙完整，低装饰且有活动开衩，可作 MUTE/LOOP 基础主衣。"),
    "g0468": ("direct_autumn_recompose", "米色长袖衬衫长裙完整，腰带收束松量，可作 EASE/LOOP 秋季主衣。"),
    "g0471": ("adjust_use_or_layer", "细肩带花纱长裙完整但暖季语汇明显；秋季须补不透内层和外层后复审。"),
    "g0474": ("occasion_only", "披肩鼓袖、刺绣、宽蝴蝶结和双色长摆同时出现，限 BOLT 礼仪场景。"),
    "g0475": ("adjust_use_or_layer", "吊带复古拼布长裙完整；秋季可配素贴身内层，冬季仍需完整外层。"),
    "g0477": ("direct_autumn_recompose", "乳白灰蓝无袖模块长裙完整；秋季配素内层，保持纵线和侧腰抽结为唯一焦点。"),
    "g0480": ("statement_not_default_daily", "左右袖与多层裙片强错位，限 OOPS/EDGE 鲜明表达并配素鞋包。"),
    "g0570": ("occasion_only", "合腰粗织夹克有披肩巨袖和礼仪装饰，限 BOLT/HEIR 场合用途。"),
    "g0573": ("blocked_item_definition", "实际图有两道独立 V 领、门襟和下摆；未能证明是单件假两件，继续隔离。"),
    "g0581": ("direct_autumn_recompose", "奶油粉绒感层裙完整且体量较厚；配素针织上衣，避免继续增加层边。"),
    "g0585": ("statement_not_default_daily", "束胸、扣眼丹宁片、链条和粉黑网纱已构成强主视觉；限 EDGE/OOPS 鲜明表达。")
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main():
    source = json.loads((AUDIT / "repair-ledger.initial.json").read_text())
    manifest = json.loads((AUDIT / "idle-main-review/manifest.json").read_text())
    assert manifest["source_ledger_version"] == source["version"]
    rows = []
    for record in source["unused_main_garments"]:
        decision, evidence = DECISIONS[record["token"]]
        rows.append({**record, "decision": decision, "native_evidence": evidence,
                     "outfit_approval": False, "winter_outdoor_approved": False})
    assert len(rows) == 35 and set(DECISIONS) == {r["token"] for r in rows}
    result = {"schema_version": 1, "source_ledger_version": source["version"],
              "review_kind": "codex_visual_review", "independent_blind_review": False,
              "sheets": manifest["sheets"], "entries": rows}
    result["version"] = "aw-idle-main-" + digest(result)[:20]
    target = AUDIT / "idle-main-review/native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    from collections import Counter
    print(json.dumps(Counter(r["decision"] for r in rows), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

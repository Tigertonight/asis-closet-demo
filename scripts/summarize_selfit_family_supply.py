"""Offline family-impact report and evidence-bound recomposition requirements."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/audits/20260903-personal-home-visual/family-review"


def summarize(family, baseline, seasons, summary):
    for report in seasons.values():
        assert report["family_registry"] == family["version"], "Stale family supply"
        assert report["visual_version"] == family["visual_version"] == baseline["visual_version"]
        assert report["strategy_version"] == baseline["strategy_version"]
        assert len(report["matrix"]) == 96
        assert all(not r["browse_thirty_diagnostics"]["constraint_violations"] for r in report["matrix"]), "Diversity violation"
    lookup = {(r["persona"], r["palette"]): r for r in baseline["matrix"]}
    changed = []
    needs = []
    per_persona = []
    for row in seasons["autumn"]["matrix"]:
        old = lookup[row["persona"], row["palette"]]
        if old["selected_ids"] != row["selected_ids"]:
            changed.append({"persona": row["persona"], "palette": row["palette"],
                            "before": old["selected_ids"], "after": row["selected_ids"]})
        if row["qualified_browse_thirty"]:
            continue
        first = row["gaps"][0] if row["gaps"] else {}
        seen = row["first_ten_structures"]
        needs.append({"persona": row["persona"], "palette": row["palette"],
            "season": "autumn", "scene": "daily", "eligible_before_sequence": row["eligible"],
            "selected_count": row["browse_thirty"], "stopped_position": first.get("position"),
            "required_expression": first.get("required_expression"),
            "structures_missing_from_current_prefix": sorted({"pants", "skirt", "dress"} - seen.keys()),
            "eligible_by_expression_structure": row["eligible_by_expression_structure"],
            "priority": "first_screen" if row["first_ten"] < 10 else "continuous_browsing",
            "required_design_change": "Add a reviewed, persona-evidenced main silhouette in this palette and required expression; shoes/bag-only or title changes do not close a structure gap.",
            "action_order": ["review_recombinations_of_unused_main_garments", "review_new_recipes_using_existing_assets", "generate_only_unresolved_new_shapes"],
            "not_proven": "A greedy stop is not proof of zero feasible combinations or a precise number of new garments required."})
    for persona in sorted({r["persona"] for r in seasons["autumn"]["matrix"]}):
        rows = [r for r in seasons["autumn"]["matrix"] if r["persona"] == persona]
        per_persona.append({"persona": persona,
            "first_ten_by_palette": {r["palette"]: r["first_ten"] for r in rows},
            "browse_thirty_by_palette": {r["palette"]: r["browse_thirty"] for r in rows},
            "stops": dict(Counter(g.get("required_expression") or "later_diversity" for r in rows for g in r["gaps"]))})
    # These are independently reviewed *garments*, not approved new outfits.
    unused_main = [r for r in summary["unused_garments"] if r["category"] in {"top", "outer", "bottom", "skirt", "dress"}]
    return {"schema_version": 1, "visual_version": family["visual_version"], "family_version": family["version"],
        "strategy_version": baseline["strategy_version"], "production_approved": False,
        "season_results": {s: {"counts": r["counts"], "palette_differentiation": r["palette_differentiation"]} for s,r in seasons.items()},
        "autumn_changed_conditions": changed, "autumn_supply_requirements": needs,
        "autumn_per_persona": per_persona, "unused_main_garment_candidates": unused_main,
        "total_conditions_checked": sum(len(r["matrix"]) for r in seasons.values()),
        "constraint_violations": 0, "independent_top1": None, "independent_top2": None,
        "limitations": ["Nonblind native AI review, not human fitting or user-study validation.",
            "Exact-descriptor synonyms, shade aliases and undiscovered family pairs limit recall.",
            "384 conditions are four seasons x daily x 16 personas x six palettes, not all scenes.",
            "Zero violations can coincide with an empty feed. Coverage and meaningful sample sizes are reported separately."]}


def markdown(report):
    lines = ["# 款式家族与有效供给：离线复核结论", "",
        f"视觉 `{report['visual_version']}` / 家族 `{report['family_version']}` / 排序 `{report['strategy_version']}`。", "",
        "结论：已有总量足够做重新编排，但尚不足以支撑所有人格和色板下稳定、准确、丰富的默认首页。家族治理不能代替设计供给，也不能靠实验款填充日常。", "",
        "## 家族与范围", "",
        "600件和1,169套已有逐项AI判断。关系复核覆盖443对机器候选、10组历史关联、6组同描述候选；13张联系表和30件原尺寸补核，共299件参与关系比较。形成68个家族、204件成员；95件在比较集内未确认家族，其余301件不在当前比较候选集。",
        "443对中78对归同家族、365对不并组。分组判定不是逐对原尺寸盲审，不是相同SKU结论，也不代表600件所有两两相似关系已穷尽。旧3个家族仍在生产配置；此处只有独立草案和离线覆盖测试。", "",
        "## 四季日常预检", "",
        "| 季节 | 首10套合格 / 96 | 连续30套合格 / 96 | 颜色可比对 | 至少变化3套 |",
        "|---|---:|---:|---:|---:|"]
    for season, data in report["season_results"].items():
        c, p = data["counts"], data["palette_differentiation"]
        lines.append(f"| {season} | {c['qualified_first_ten']} | {c['qualified_browse_thirty']} | {p['comparable_pairs']} | {p['changed_at_least_three']} |")
    lines += ["", f"秋季有 **{len(report['autumn_changed_conditions'])} / 96** 个条件的选中序列因家族草稿发生变化。虽然达标条件总数未变，不能据此说家族约束没有作用。",
        "共384条条件，已选序列的连续10套主单品/家族上限与父配方间距零违规。但空列表也可能零违规；这不证明用户体验达标。贪心未找到不代表数学上没有可行解，颜色可比对不足时不能外推全条件80%验收。", "",
        "## 秋季人格 × 色板的实际前缀长度", "",
        "每格为当前策略找到的首轮数量，上限10；不是该人格总库存。mono=黑白灰，earth=大地，ocean=蓝调，jewel=宝石，bright=鲜亮，pastel=浅柔。", "",
        "| 人格 | mono | earth | ocean | jewel | bright | pastel | 主要停止位置所需表达 |",
        "|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in report["autumn_per_persona"]:
        counts = row["first_ten_by_palette"]
        lines.append("| " + row["persona"].upper() + " | " + " | ".join(str(counts[k]) for k in ("mono","earth","ocean","jewel","bright","pastel")) + " | " + ", ".join(f"{k}:{v}" for k,v in row["stops"].items()) + " |")
    lines += ["", "## 定向补齐，不按总量盲目生产", "",
        f"- 秋季 **{len(report['autumn_supply_requirements'])}** 条条件未达到连续30套；完整条件、停止位、表达和现有结构数量见 `family-supply-summary.json` 的 `autumn_supply_requirements`。",
        f"- 先盘活 **{len(report['unused_main_garment_candidates'])}** 件未进入生效配方的主服装，逐件证据保留在 `unused_main_garment_candidates`。不能因为单品合格直接批准新组合；剩余帽围巾配饰不强行填槽。",
        "- 第一组：BOLT、EDGE、NEON、OOPS、VOID的默认日常易穿入口。保持各自结构证据，同时降低多焦点竞争；不能只给基础衣服换上夸张包鞋。",
        "- 第二组：JADE / LOOP的主服装家族与比例。JADE g0172在73套中复用32次；优先不同裙裤/连衣装和长短关系，不只换标题或鞋包。",
        "- 第三组：FILM / FLOU / MUTE等停在典型或轻探索位的条件。保持偏好色与排除项，在相近风格内改变一个主要廓形或层次，不能拿实验款冒充轻探索。",
        "- 第四组：颜色与季节缺口。秋季bright的各人格条件目前均未组成首页；冬季所有条件未组成合格首轮。这是当前审核证据、门槛与选择器共同结果，不能简单推断成只缺几件亮色衣服或全库冬装为零。",
        "- 排序复核：固定表达位遇缺口会提前终止；应离线评估带前瞻的编排能否改善既有供给，不降低适配门槛、不放宽家族上限。此报告没有更改运行策略。", "",
        "## 人格区分与问题配方", "",
        "目录标签不是视觉真相。逐套记录及并列最强人格见上级 `full-native-audit-summary.json`，具体例子：FILM目录有23套最强观察为VOID；NEON有16套为EDGE、7套为OOPS；JADE有30套更支持EASE。这是非盲AI观察计数，不是已验证的误标率或独立准确率。",
        "问题配方217套保留原资产与证据：多焦点竞争、外内袖量、透明主衣内搭、季节/正式度及鞋跟平衡应分别修正，不能批量同判。33套建议排除默认验证；178套需复核；6套自身为候选但关联单品未通过。",
        "7件待核单品不因家族关系而晋级。用户所需的体型/肤色适配、真实试穿成功率、Top-1/Top-2盲审和真实满意度仍需后续验证。", "",
        "## 文件与复现", "",
        "- `native-family-review.json`：逐对结论、成员证据、历史候选拆并与文件指纹。",
        "- `garment-style-families.native-draft.json`：仅供离线测试的注册草稿。",
        "- `effective-coverage-{season}.json`：96条条件及实际选中ID、主色/鞋包/轮廓/家族相似度。",
        "- `family-supply-summary.json`：前后序列差异、定向需求和未使用主服装候选。", "",
        "运行项目虚拟环境下 `scripts/compile_selfit_family_review.py`、`scripts/audit_selfit_personal_home_supply.py --season <season> --family-registry <draft> --output <report>`，最后执行 `scripts/summarize_selfit_family_supply.py`。",
        "审核与离线验算完成不等于产品路线完成或批准上线；不涉及提交、推送、生产部署或人格分型算法变更。", ""]
    return "\n".join(lines)


def main():
    read = lambda p: json.loads(p.read_text())
    family = read(DIRECTORY / "native-family-review.json")
    seasons = {s: read(DIRECTORY / f"effective-coverage-{s}.json") for s in ("spring", "summer", "autumn", "winter")}
    report = summarize(family, read(DIRECTORY.parent / "effective-coverage-autumn.json"), seasons,
                       read(DIRECTORY.parent / "full-native-audit-summary.json"))
    (DIRECTORY / "family-supply-summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (DIRECTORY / "FAMILY_AND_SUPPLY_REVIEW.md").write_text(markdown(report))
    print(json.dumps({"changed_conditions": len(report["autumn_changed_conditions"]),
                      "gap_conditions": len(report["autumn_supply_requirements"]),
                      "unused_main": len(report["unused_main_garment_candidates"])}))


if __name__ == "__main__":
    main()

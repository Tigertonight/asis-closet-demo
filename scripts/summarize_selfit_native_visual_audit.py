"""Aggregate recorded native image judgments, without inventing visual labels.

This offline report neither edits the content pool nor activates style families.
Catalog persona is a comparison target, not independent ground truth. Descriptor
groups and unreviewed machine pairs remain candidates, never family approvals.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_profile import digest

STYLE_FIELDS = ("category", "subcategory", "neckline", "sleeve", "length", "volume",
                "construction", "pattern", "material_appearance")


def aggregate(visual, pool, coverage, registry, family_notes, machine_pairs, family_review=None, draft_coverage=None):
    assert coverage["visual_version"] == visual["version"], "Stale coverage report"
    for section in ("garments", "outfits"):
        assert all(r.get("review_complete") for r in visual[section].values()), "Incomplete native audit"
    raw = {section: {r["id"]: r for r in pool[section]} for section in ("garments", "outfits")}
    garments, outfits = visual["garments"], visual["outfits"]
    assert set(garments) <= set(raw["garments"]) and set(outfits) <= set(raw["outfits"])
    usage = Counter(gid for oid in outfits for gid in raw["outfits"][oid]["garment_ids"])
    by_persona, confusion, problems = defaultdict(list), defaultdict(Counter), []
    for oid, record in outfits.items():
        fields = record["observations"]
        declared = raw["outfits"][oid]["primary_persona"].lower()
        scores = fields["persona_scores"]
        maximum = max(scores.values())
        strongest = sorted(p for p, score in scores.items() if score == maximum)
        # Preserve ties, do not award an arbitrary alphabetic Top-1 winner.
        confusion[declared][" / ".join(strongest)] += 1
        item = {"outfit_id": oid, "token": record["token"], "status": record["status"],
                "parent_recipe": raw["outfits"][oid].get("parent_outfit_id") or oid,
                "catalog_persona": declared, "catalog_persona_visual_score": scores.get(declared),
                "strongest_observed_personas": strongest, "visual_scores": scores,
                "structure": fields["structure"], "expression": fields["expression"],
                "seasons": fields.get("seasons"), "scenes": fields.get("scenes"),
                "evidence": fields.get("persona_evidence"), "source_file": record["source_file"]}
        by_persona[declared].append(item)
        held_garments = [gid for gid in raw["outfits"][oid]["garment_ids"]
                         if garments[gid]["status"] != "ai_candidate"]
        if record["status"] != "ai_candidate" or held_garments:
            problems.append({**item, "conflicts": fields.get("conflicts") or [],
                             "held_garment_ids": held_garments, "visual_evidence": record["evidence"],
                             "action": "preserve_asset_and_history_revise_recipe_then_reaudit"})
    persona_rows = []
    for persona, rows in sorted(by_persona.items()):
        ids = {r["outfit_id"] for r in rows}
        used = {gid for oid in ids for gid in raw["outfits"][oid]["garment_ids"]}
        counts = Counter(gid for oid in ids for gid in raw["outfits"][oid]["garment_ids"]
                         if garments[gid]["observations"]["category"] in {"top", "outer", "bottom", "skirt", "dress"})
        persona_rows.append({"persona": persona, "outfits": len(rows), "garments_used": len(used),
            "parent_recipes": len({r["parent_recipe"] for r in rows}),
            "statuses": dict(Counter(r["status"] for r in rows)),
            "structures": dict(Counter(r["structure"] for r in rows)),
            "expressions": dict(Counter(r["expression"] for r in rows)),
            "declared_score_unknown": sum(r["catalog_persona_visual_score"] is None for r in rows),
            "declared_score_below_runtime_gate": sum(r["catalog_persona_visual_score"] is not None and
                r["catalog_persona_visual_score"] < .55 for r in rows),
            "largest_main_item_reuse": [{"garment_id": g, "token": garments[g]["token"], "outfits": n}
                                         for g, n in counts.most_common(5)],
            "observed_persona_confusion": dict(confusion[persona])})
    descriptor_groups = defaultdict(list)
    unknown_styles = []
    for gid, record in garments.items():
        fields = record["observations"]
        key = tuple(fields.get(k) for k in STYLE_FIELDS)
        if any(value is None for value in key):
            unknown_styles.append(gid)
        else:
            descriptor_groups[key].append(gid)
    groups = [{"id": "descriptor-candidate:" + digest(key)[:12], "dimensions": dict(zip(STYLE_FIELDS, key)),
               "members": [{"garment_id": gid, "token": garments[gid]["token"],
                            "main_colors": garments[gid]["observations"].get("main_colors"),
                            "asset_sha256": garments[gid]["asset_sha256"],
                            "source_file": garments[gid]["source_file"]} for gid in sorted(gids)],
               "status": "candidate_only_requires_pairwise_visual_review"}
              for key, gids in descriptor_groups.items() if len(gids) > 1]
    groups.sort(key=lambda x: (-len(x["members"]), x["id"]))
    unused = [{"garment_id": gid, "token": r["token"], "status": r["status"],
               "category": r["observations"]["category"], "visual_personas": r["observations"].get("visual_personas"),
               "main_colors": r["observations"].get("main_colors"), "evidence": r["evidence"]}
              for gid, r in garments.items() if not usage[gid]]
    gaps = [{**r, "action": "recombine_audited_assets_then_review_new_recipe_before_new_generation"}
            for r in coverage["matrix"] if not r["qualified_first_ten"] or not r["qualified_browse_thirty"]]
    if family_review is not None:
        assert family_review["visual_version"] == visual["version"], "Stale family review"
        assert family_review["machine_pairs_all_adjudicated"] is True
        assert len(family_review["machine_pair_decisions"]) == len(machine_pairs), "Incomplete family queue"
        assert {tuple(sorted((p["left"], p["right"]))) for p in family_review["machine_pair_decisions"]} == {tuple(sorted((p["left"], p["right"]))) for p in machine_pairs}, "Mismatched family queue"
    if draft_coverage is not None:
        assert family_review and draft_coverage["visual_version"] == visual["version"] and draft_coverage["family_registry"] == family_review["version"], "Stale draft coverage"
    return {"schema_version": 1, "visual_version": visual["version"], "strategy_version": coverage["strategy_version"],
        "scope": "All 600 garments and 1169 active outfits have explicit native image judgments; " + ("all queued family candidates adjudicated in an offline draft. All-pairs recall, blind accuracy and real fitting remain unknown." if family_review else "global family candidate governance is pending."),
        "human_reviewed": False, "independent_blind_review": False, "publish_approval": False,
        "independent_top1": None, "independent_top2": None,
        "limitations": ["Visual affinity is subjective/nonblind, not probability or measured accuracy.",
            "Missing persona scores are unknown, not zero. Tied strongest personas are preserved.",
            "Exact text descriptors can miss synonyms and overgroup distinct details; never auto-merge.",
            "Coverage uses current greedy selection and production families, not maximum feasible supply.",
            "Candidate outfits include experimental looks; candidate count is not default daily capacity."],
        "completion": visual["completion"], "counts": visual["counts"],
        "effective_coverage": coverage["counts"], "palette_differentiation": coverage["palette_differentiation"],
        "persona_supply": persona_rows, "persona_evidence_ledger": [r for rows in by_persona.values() for r in rows],
        "problem_outfits": problems, "problem_conflict_counts": dict(Counter(c for r in problems for c in r["conflicts"])),
        "unused_garments": unused, "unused_categories": dict(Counter(r["category"] for r in unused)),
        "family_governance": {"active_registry_family_count": len(registry.get("families", [])),
            "active_registry_member_count": len({g for f in registry.get("families", []) for g in f["members"]}),
            "recorded_native_relationships": family_notes, "strict_descriptor_candidates": groups,
            "unknown_descriptor_garments": unknown_styles, "machine_pair_queue_count": len(machine_pairs),
            "machine_pairs": machine_pairs, "machine_pairs_all_reviewed": family_review is not None, "activated_by_this_report": False,
            "native_review": {"version": family_review["version"], "counts": family_review["counts"], "methods": family_review["methods"]} if family_review else None},
        "offline_draft_coverage": draft_coverage,
        "supply_gaps": gaps}


def markdown(report):
    counts, effective = report["counts"], report["effective_coverage"]
    family = report["family_governance"]
    lines = ["# Selfit 全量原生看图审核：汇总与治理缺口", "",
        f"审核版本：`{report['visual_version']}`；排序版本：`{report['strategy_version']}`。", "",
        "600 件单品和 1,169 套生效穿搭已全部有逐项原图/联系表视觉证据。疑点查看原尺寸；不是每套均做原尺寸检查。",
        "这是非盲 AI 审核，不是人工审核、实穿验证或独立人格命中率。全量逐项记录完成；" + ("家族候选队列也已有分组比较判定，但产品优化与生产发布尚未完成。" if family.get("native_review") else "全局家族队列与产品路线尚未完成。"), "",
        "## 1. 准入与有效供给", "",
        f"- 单品：{counts['garments'].get('ai_candidate', 0)} 件候选，{counts['garments'].get('needs_review', 0)} 件需复核。",
        f"- 穿搭：{counts['outfits'].get('ai_candidate', 0)} 套候选，{counts['outfits'].get('needs_review', 0)} 套需复核，{counts['outfits'].get('suggested_exclude', 0)} 套建议排除默认验证。",
        f"- 整套及关联单品均满足当前证据门槛：{effective['visual_candidate_outfits']} 套；其中仍包含仅限非日常的实验款。",
        f"- 秋季日常 96 条条件：首轮 10 套合格 {effective['qualified_first_ten']}/96，连续 30 套合格 {effective['qualified_browse_thirty']}/96。",
        "- 结果仅证明当前贪心策略找到的供给；未找到不证明一定无可行解。生产家族尚不完整，因此也不能宣称体感相似度达标。", "",
        "## 2. 人格归属与视觉证据偏移", "",
        "下表按原目录主人格分组。低于 0.55 是与当前运行门槛比较，不是误判率；未记录的分数另列未知，不当零分。", "",
        "| 目录人格 | 组合 | 父配方 | 使用单品 | 视觉候选 | 原人格分低于门槛 | 未知 |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["persona_supply"]:
        lines.append(f"| {r['persona'].upper()} | {r['outfits']} | {r['parent_recipes']} | {r['garments_used']} | {r['statuses'].get('ai_candidate',0)} | {r['declared_score_below_runtime_gate']} | {r['declared_score_unknown']} |")
    lines += ["", "主服装重复最多的目录人格（全库配方复用计数，不是连续推荐重复违规）：", ""]
    repeated = sorted(report["persona_supply"], key=lambda r: r["largest_main_item_reuse"][0]["outfits"], reverse=True)
    for row in repeated[:3]:
        item = row["largest_main_item_reuse"][0]
        lines.append(f"- {row['persona'].upper()}：`{item['token']}` 在 {row['outfits']} 套中出现 {item['outfits']} 次；应先扩展主结构，不靠替换鞋包计新款。")
    lines += ["", "完整主人格→观察最强人格交叉计数、并列值和逐套证据见 JSON 的 `persona_supply` / `persona_evidence_ledger`。不得称为独立混淆矩阵的准确率。", "",
        "## 3. 相似性与款式家族", "",
        f"- 当前生产注册：{family['active_registry_family_count']} 个家族、{family['active_registry_member_count']} 件成员。没有在本报告中激活新家族。",
        f"- 已记录原生关系候选：{len(family['recorded_native_relationships'])} 组；逐项视觉字段完全同文的候选：{len(family['strict_descriptor_candidates'])} 组。两者可能重叠，不能相加当作独立家族数。",
        f"- 历史机器近似队列：{family['machine_pair_queue_count']} 对，" + ("已全部按原生看图分组给出关系判定；并非每对都单独查看原尺寸。" if family.get("native_review") else "尚未全量逐对视觉确认。"),
        "- 同词字段分组不是同版型认定；同义词、透视和松量细节可能漏合或误合。候选成员保留指纹和颜色，禁止自动合并资产。", "",
        "## 4. 问题配方与闲置单品", "",
        f"- 问题清单共 {len(report['problem_outfits'])} 套（含整套候选但关联单品待核实），逐套保留冲突及建议动作。",
        f"- 生效穿搭尚未使用 {len(report['unused_garments'])} 件，品类分布：`{json.dumps(report['unused_categories'], ensure_ascii=False)}`。",
        "- 不将帽子、围巾强行加到所有配方。先选择人格/色板/结构明确缺口，重组后重新看整套，而不是继承单品候选状态。", "",
        "## 5. 下一阶段优先顺序", "",
        "1. 按 `supply_gaps` 定位当前季节下缺少的易穿、典型、轻探索与主结构，不按总量盲目生图。",
        "2. 优先给 LOOP / JADE 增加有实际使用的不同裤、裙和连衣装比例；共享基础款不应只靠换鞋包定义人格。",
        "3. 将 NEON 的高彩能量、EDGE 的甜酷锐利、OOPS 的主动错位拆开；把默认日常与创意实验分别供给。",
        "4. 家族草稿先用于内部验证及边界复核，不自动激活生产；维持主单品/家族上限，不为凑数放宽。" if family.get("native_review") else "4. 复核家族候选并生成独立草稿注册表，再重新运行96条条件，不为凑数放宽。",
        "5. 对多焦点、内层覆盖、袖量及成对鞋平衡问题分别修正配方后重审；原素材和历史保留。", "",
        "独立人格 Top-1 / Top-2、真人穿着与体感改善仍未知。新策略默认关闭；本报告不构成生产发布授权。", ""]
    if family.get("native_review"):
        native, coverage = family["native_review"], report["offline_draft_coverage"]
        counts = native["counts"]
        lines += ["## 6. 家族复核与离线重算", "",
            f"草稿版本 `{native['version']}`。13 张对照表覆盖机器候选的278件，补充历史关联和同描述候选后共{counts['reviewed_members']}件；{len(native['methods']['full_resolution_viewed'])}件额外原尺寸检查。", "",
            f"- 草稿：{counts['draft_families']}个多成员家族、{counts['family_members']}件成员；{counts['comparison_singletons']}件比较内未确认同家族。其余{counts['not_in_comparison_set']}件有逐项审核，但不在本次关系候选集，不能宣称全局独特。",
            f"- 443对关系判定：同家族{counts['pair_decisions'].get('same_visual_family',0)}对，不并组{counts['pair_decisions'].get('distinct_visual_family',0)}对。不同家族仍可能共享设计语言，不代表零相似。",
            "- 历史10组关系、6组同文描述候选均已对照；全量两两相似性召回率仍未知。不会按机器连通分量自动并组，不修改单品QA。",
            "- 原尺寸把g0511敞弧口软肩包与g0527抽绳桶包拆开；g0592信使包从g0512/g0528软肩包组拆开，保留材料关联。",
            "- 详见 [家族判定与草稿](family-review/native-family-review.json) 及 [离线四季与定向缺口](family-review/FAMILY_AND_SUPPLY_REVIEW.md)。", ""]
        if coverage:
            c = coverage["counts"]
            lines += [f"秋季日常草稿约束下：首10套{c['qualified_first_ten']}/96、连续30套{c['qualified_browse_thirty']}/96。颜色可比{coverage['palette_differentiation']['comparable_pairs']}对，不能据此宣称全用户条件通过。",
                "达标条件总数未变不代表排序没变；对照包含实际选中ID、款式家族相似度、主色出现占比、鞋包重复和约束检查。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT / "docs/audits/20260903-personal-home-visual")
    args = parser.parse_args()
    directory = args.directory
    read = lambda p: json.loads(p.read_text())
    notes = []
    for path in sorted(directory.glob("codex-family-observations-*.tsv")):
        with path.open() as handle:
            notes.extend({**r, "source_file": path.name} for r in csv.DictReader(handle, delimiter="\t"))
    report = aggregate(read(ROOT / "app/data/recommendation-visual.v1.json"),
        read(ROOT / "app/static/selfit/data/content-pool.v2.published.json"),
        read(directory / "effective-coverage-autumn.json"),
        read(ROOT / "app/data/garment-style-families.v1.json"), notes,
        read(ROOT / "docs/audits/20260903-recommendation-similarity/audit-data.json")["garment_similarity"]["joint_pairs"],
        read(directory / "family-review/native-family-review.json") if (directory / "family-review/native-family-review.json").exists() else None,
        read(directory / "family-review/effective-coverage-autumn.json") if (directory / "family-review/effective-coverage-autumn.json").exists() else None)
    (directory / "full-native-audit-summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (directory / "FULL_NATIVE_AUDIT_SUMMARY.md").write_text(markdown(report))
    print(json.dumps({"visual_version": report["visual_version"], "problems": len(report["problem_outfits"]),
                      "unused_garments": len(report["unused_garments"]), "gap_conditions": len(report["supply_gaps"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()

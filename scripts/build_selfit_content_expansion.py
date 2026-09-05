#!/usr/bin/env python3
"""Build the decision-complete 600-garment / 1,200-outfit production plan.

This script creates production jobs and recipe manifests only.  Planned jobs
are never treated as published content; the publisher separately requires real
files and approved QA records.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import record_fingerprint
CATALOG = ROOT / "app/static/selfit/data/content-generation-prompts.v1.json"
REFERENCES = ROOT / "app/static/selfit/data/reference-looks.internal.json"
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"
DEFAULT_QUEUE = ROOT / "docs/SELFIT_IMAGEGEN_PROMPT_QUEUE_V2.jsonl"

PERSONAS = ("MUTE", "ICED", "HEIR", "EASE", "MELT", "WABI", "FLOU", "NEON", "EDGE", "BOLT", "FILM", "JADE", "LOOP", "NOIR", "VOID", "OOPS")
CATEGORY_QUOTAS = {
    "top": 120, "outer": 80, "bottom": 70, "skirt": 70, "dress": 60,
    "shoes": 70, "bag": 60, "hat": 30, "scarf": 20, "accessory": 20,
}
SCENE_QUOTA = ["通勤"] * 6 + ["日常"] * 6 + ["约会社交"] * 5 + ["正式活动"] * 4 + ["旅行"] * 4 + ["创意表达"] * 5
SEASON_QUOTA = ["春"] * 7 + ["夏"] * 8 + ["秋"] * 8 + ["冬"] * 7
INTENSITY_QUOTA = ["entry"] * 12 + ["signature"] * 12 + ["experimental"] * 6
PRESENTATION_QUOTA = ["feminine"] * 21 + ["neutral"] * 9

ITEM_NAMES = {
    "top": ["直线府绸衬衫", "细针织上衣", "短款圆领上衣", "垂坠罩衫", "无袖背心", "克制花纹衬衫"],
    "outer": ["短款结构外套", "无领西装", "长线条风衣", "柔软针织开衫", "轻量夹克", "茧型大衣"],
    "bottom": ["高腰直筒裤", "垂坠阔腿裤", "九分锥形裤", "低腰宽裤", "利落烟管裤", "水洗牛仔裤"],
    "skirt": ["高腰A字半裙", "窄长半裙", "斜裁中长裙", "百褶半裙", "结构短裙", "层叠长裙"],
    "dress": ["纵向衬衫裙", "斜裁连衣裙", "收腰中长连衣裙", "直筒连衣裙", "轻层叠长裙", "结构迷你连衣裙"],
    "shoes": ["低跟乐福鞋", "尖头短靴", "圆头玛丽珍鞋", "轻量运动鞋", "细带低跟鞋", "结构长靴"],
    "bag": ["中号结构手袋", "柔软肩背包", "几何托特包", "小型腋下包", "轻量邮差包", "抽绳手袋"],
    "hat": ["软呢帽", "克制贝雷帽", "结构棒球帽", "窄檐帽", "针织软帽"],
    "scarf": ["窄幅丝巾", "轻薄长围巾", "柔软披肩", "纹理针织围巾"],
    "accessory": ["几何耳饰", "细腰带", "克制项链", "模块胸针", "细框眼镜"],
}

ADJACENT = {
    "MUTE": ("ICED", "HEIR"), "ICED": ("MUTE", "FLOU"), "HEIR": ("EASE", "MUTE"), "EASE": ("HEIR", "WABI"),
    "MELT": ("FLOU", "EASE"), "WABI": ("EASE", "VOID"), "FLOU": ("MELT", "BOLT"), "NEON": ("EDGE", "OOPS"),
    "EDGE": ("NEON", "NOIR"), "BOLT": ("FLOU", "HEIR"), "FILM": ("WABI", "EASE"), "JADE": ("MUTE", "WABI"),
    "LOOP": ("MUTE", "EASE"), "NOIR": ("EDGE", "MUTE"), "VOID": ("WABI", "FILM"), "OOPS": ("NEON", "EDGE"),
}

COLOR_RULES = {
    "MUTE": ("中性", "中等", "无彩", "无彩平衡"), "ICED": ("冷调", "浅色", "低饱和", "邻近色"),
    "HEIR": ("暖调", "中等", "低饱和", "主色加点缀"), "EASE": ("暖调", "中等", "低饱和", "邻近色"),
    "MELT": ("暖调", "浅色", "低饱和", "同色"), "WABI": ("中性", "中等", "低饱和", "邻近色"),
    "FLOU": ("冷暖混合", "浅色", "低饱和", "邻近色"), "NEON": ("冷暖混合", "深浅对比", "高饱和", "互补色"),
    "EDGE": ("冷调", "深浅对比", "中饱和", "主色加点缀"), "BOLT": ("暖调", "深浅对比", "中饱和", "主色加点缀"),
    "FILM": ("暖调", "中等", "低饱和", "邻近色"), "JADE": ("中性", "深浅对比", "低饱和", "主色加点缀"),
    "LOOP": ("中性", "中等", "低饱和", "主色加点缀"), "NOIR": ("冷调", "深色", "无彩", "无彩平衡"),
    "VOID": ("中性", "深色", "低饱和", "混合"), "OOPS": ("冷暖混合", "深浅对比", "高饱和", "混合"),
}

CATEGORY_LOCKS = {
    "top": "one upper-body top garment only; not a dress, jacket, bag, bottom or accessory",
    "outer": "one outerwear garment only; not a top, dress, bag, bottom or accessory",
    "bottom": "one pair of trousers only; not a skirt, dress, top, bag or accessory",
    "skirt": "one separate skirt only with a continuous front panel and no inseam or leg bifurcation; not shorts, skorts, trousers, a dress, top, bag or accessory",
    "dress": "one complete one-piece dress with a clearly visible upper bodice, neckline or shoulder straps physically attached to the skirt section; never a standalone skirt, separates, shoes, a bag or an accessory",
    "shoes": "one matching pair of wearable shoes as a single product; not clothing, a dress or a bag",
    "bag": "one wearable handbag as a single product; not clothing, a jacket, dress, shoes or accessory set",
    "hat": "one wearable hat only; not clothing, a bag or another accessory",
    "scarf": "one scarf only; not clothing, a bag or another accessory",
    "accessory": "one accessory product only; not clothing, shoes or a bag",
}

SHARED_VARIATIONS = {
    "top": ("clean hidden placket", "small pointed collar", "soft band collar", "single minimal chest pocket", "slightly elongated hem", "subtle curved hem"),
    "outer": ("single-breasted closure", "clean collarless front", "compact lapel", "minimal patch pockets", "slightly cropped proportion", "long straight proportion"),
    "bottom": ("flat front", "single front pleat", "clean pressed crease", "slightly tapered leg", "relaxed straight leg", "subtle cropped length"),
    "skirt": ("clean A-line", "straight midi line", "single restrained pleat", "subtle bias line", "flat waistband", "minimal wrap construction"),
    "dress": ("clean shirt-dress line", "straight midi line", "restrained waist shaping", "subtle bias line", "minimal sleeveless column", "soft long-sleeve line"),
    "shoes": ("clean rounded toe", "subtle square toe", "low stacked heel", "flat minimal sole", "single slender strap", "plain loafer construction"),
    "bag": ("clean rectangular body", "soft crescent body", "small structured tote", "minimal shoulder bag", "compact bucket body", "plain crossbody body"),
    "hat": ("clean narrow brim", "soft rounded crown", "minimal six-panel form", "plain knitted crown", "restrained beret form"),
    "scarf": ("plain narrow rectangle", "soft long rectangle", "small square silk form", "lightweight tonal edge", "subtle woven texture"),
    "accessory": ("single clean geometric form", "one restrained curved form", "minimal linear construction", "small tonal detail", "plain polished surface"),
}


def _category(name: str) -> str:
    rules = (("shoes", ("鞋", "靴")), ("bag", ("包", "手袋", "托特", "肩背", "腋下", "邮差")), ("bottom", ("裤",)), ("dress", ("连衣", "泡袖裙", "旗袍")),
             ("skirt", ("裙",)), ("outer", ("外套", "大衣", "风衣", "西装", "皮衣", "夹克", "斗篷", "开衫")),
             ("hat", ("帽",)), ("scarf", ("围巾", "披肩")), ("accessory", ("配饰", "腰带", "首饰", "胸针")))
    return next((category for category, terms in rules if any(term in name for term in terms)), "top")


def _allocate(total: int, capacities: dict[str, int]) -> Counter[str]:
    capacity_total = sum(capacities.values())
    exact = {key: total * value / capacity_total for key, value in capacities.items()}
    result = Counter({key: min(value, int(exact[key])) for key, value in capacities.items()})
    while sum(result.values()) < total:
        candidates = [key for key in capacities if result[key] < capacities[key]]
        key = max(candidates, key=lambda item: (exact[item] - result[item], capacities[item] - result[item], item))
        result[key] += 1
    return result


def _reference_index() -> dict[str, list[str]]:
    if not REFERENCES.exists():
        return {}
    data = json.loads(REFERENCES.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = defaultdict(list)
    for item in data.get("reference_looks", []):
        codes = [item.get("primary_persona"), *(item.get("secondary_personas") or [])]
        for code in codes:
            if code in PERSONAS:
                result[str(code)].append(str(item["id"]))
    return result


def _job(*, index: int, persona: str, category: str, tier: str, name: str, profile: dict[str, Any], references: dict[str, list[str]]) -> dict[str, Any]:
    job_id = f"v2_{index:04d}_{persona.lower()}_{category}"
    seasons = ["四季"] if tier == "shared" else [["春", "夏"], ["秋", "冬"], ["四季"]][index % 3]
    scenes = ["通勤", "日常", "约会社交", "正式活动", "旅行", "创意表达"] if tier == "shared" else [["通勤", "日常"], ["约会社交", "正式活动"], ["旅行", "创意表达"]][index % 3]
    affinity = {persona: 0.96 if tier == "signature" else (0.88 if tier == "variant" else 0.82), ADJACENT[persona][0]: 0.66, ADJACENT[persona][1]: 0.56}
    reference_ids = [] if persona in {"LOOP", "OOPS"} else (references.get(persona, [])[:1] if references.get(persona) else [])
    if tier == "shared":
        design_direction = "简洁、比例标准、容易叠穿，作为多个相邻人格都能复用的衣橱基础款"
        palette = "烟白、炭灰、海军蓝、灰褐、浅蓝等低饱和中性色，只使用一个主色"
        materials = "按品类选择棉府绸、细针织、精纺羊毛、洁净牛仔、哑光皮革或细腻帆布"
        design_avoid = "夸张印花、拼布、荷叶边、束身结构、装饰绑带、亮色撞色、复杂不对称和实验性解构"
        request_name = name.removeprefix(profile["name"])
        tier_context = "cross-persona shared foundation"
        variation_cue = SHARED_VARIATIONS[category][(index // len(ITEM_NAMES[category])) % len(SHARED_VARIATIONS[category])]
        shared_cue = f"Shared variation cue: {variation_cue}. Subtle affinity code: {persona}; use only one muted undertone from {profile['palette']}, never signature styling.\n"
    else:
        design_direction = profile["silhouette"]
        palette = profile["palette"]
        materials = profile["materials"]
        design_avoid = profile["avoid"]
        request_name = name
        tier_context = tier
        shared_cue = ""
    prompt = (
        "Use case: product-mockup\nAsset type: Selfit original wardrobe garment cutout\n"
        f"Primary request: create exactly one original 女装单品：{request_name}。"
        f"廓形方向：{design_direction}。层级：{tier_context}。\n"
        f"Category lock: {CATEGORY_LOCKS[category]}. The depicted product must match this category literally.\n"
        f"{shared_cue}"
        "Scene/backdrop: genuinely transparent background\n"
        "Subject: exactly one isolated garment, front-facing, naturally shaped as if invisibly supported; original unbranded design\n"
        "Style/medium: photorealistic premium fashion e-commerce product photography\n"
        "Composition/framing: centered square canvas, complete silhouette, 12% clear padding on every side, no crop\n"
        f"Lighting/mood: soft neutral studio light\nColor palette: {palette}\nMaterials/textures: {materials}\n"
        "Constraints: actual transparent alpha; no person, mannequin, hanger, stand, text, label, logo or watermark; do not reproduce identifiable patterns or branded design from any reference\n"
        f"Avoid: clipped edges, duplicate items, extra accessories, fake white background; {design_avoid}"
    )
    slug = f"{persona.lower()}-{category}-{index:04d}"
    tone, lightness, saturation, harmony = COLOR_RULES[persona]
    return {
        "job_id": job_id,
        "status": "planned",
        "wave": "signature_pilot" if index <= 80 else tier,
        "tier": tier,
        "persona": persona,
        "category": category,
        "garment_name": name,
        "reference_ids": reference_ids,
        "execution": "one built-in imagegen call",
        "expected_raw_output": f"app/static/selfit/assets/content_v2/{persona.lower()}/garments/{slug}-raw-v1.png",
        "expected_output": f"app/static/selfit/assets/content_v2/{persona.lower()}/garments/{slug}-v1.png",
        "prompt": prompt,
        "record_template": {
            "id": f"garment_{slug.replace('-', '_')}", "category": category, "subcategory": name,
            "silhouette": [profile["silhouette"]], "fit": "不适用" if category in {"shoes", "bag", "hat", "scarf", "accessory"} else "合体",
            "materials": [profile["materials"]], "details": [f"{tier}原创款"], "season_tags": seasons, "scene_tags": scenes,
            "weather_tags": ["晴", "室内"], "presentation": ["feminine", "neutral"],
            "layer_role": "outer" if category == "outer" else ("accessory" if category in {"shoes", "bag", "hat", "scarf", "accessory"} else "single"),
            "tryon_slot": category, "persona_affinity": affinity,
            "color": {"temperature": tone, "lightness": lightness, "saturation": saturation, "harmony": harmony, "palette": []},
            "assets": {"image_url": "/static/" + f"selfit/assets/content_v2/{persona.lower()}/garments/{slug}-v1.png", "source_url": "", "width": 1200, "height": 1200, "alpha_verified": False, "rights_status": "owned"},
            "production": {"source_kind": "generated_original", "generation_job_id": job_id, "prompt_version": "selfit-garment-v2.1", "reference_ids": reference_ids, "qa_status": "planned", "phash": ""},
            "annotation": {"status": "unlabeled", "source": "designer", "confidence": 0.0, "review_notes": ["等待生图与视觉审核"]},
        },
    }


def build_garment_jobs(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    references = _reference_index()
    jobs: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    index = 0
    for persona in PERSONAS:
        profile = catalog["personas"][persona]
        for signature in profile["signature"]:
            index += 1
            category = _category(signature)
            counts[category] += 1
            jobs.append(_job(index=index, persona=persona, category=category, tier="signature", name=signature, profile=profile, references=references))
    remaining = {key: CATEGORY_QUOTAS[key] - counts[key] for key in CATEGORY_QUOTAS}
    for tier, total in (("shared", 240), ("variant", 240), ("signature", 40)):
        allocation = _allocate(total, remaining)
        for category in CATEGORY_QUOTAS:
            for _ in range(allocation[category]):
                index += 1
                persona = PERSONAS[(index - 1) % len(PERSONAS)]
                profile = catalog["personas"][persona]
                names = ITEM_NAMES[category]
                # Rotate the product archetype per job. Grouping sixteen personas
                # under one archetype made shared assets near-identical recolors.
                base = names[index % len(names)]
                name = f"{profile['name']}{base}"
                jobs.append(_job(index=index, persona=persona, category=category, tier=tier, name=name, profile=profile, references=references))
                remaining[category] -= 1
    assert len(jobs) == 600
    assert Counter(job["category"] for job in jobs) == Counter(CATEGORY_QUOTAS)
    assert Counter(job["tier"] for job in jobs) == Counter({"shared": 240, "variant": 240, "signature": 120})
    return jobs


def _eligible(jobs: list[dict[str, Any]], persona: str, category: str, season: str, scene: str) -> list[dict[str, Any]]:
    items = [job for job in jobs if job["category"] == category and persona in job["record_template"]["persona_affinity"]]
    strict = [job for job in items if season in job["record_template"]["season_tags"] or "四季" in job["record_template"]["season_tags"]]
    strict_scene = [job for job in strict if scene in job["record_template"]["scene_tags"]]
    ordered = [*strict_scene, *strict, *items, *[job for job in jobs if job["category"] == category]]
    seen = set()
    return [job for job in ordered if not (job["job_id"] in seen or seen.add(job["job_id"]))]


def _master_composition(index: int) -> list[str]:
    if index < 10:
        return ["top", "bottom", "shoes", "bag"]
    if index < 18:
        return ["top", "skirt", "shoes", "bag"]
    if index < 24:
        return ["top", "bottom", "outer", "shoes", "bag"]
    return ["dress", "shoes", "bag", "accessory"]


def _choose(
    candidates: list[dict[str, Any]],
    persona: str,
    season: str,
    scene: str,
    usage: Counter[str],
    recent: Counter[str] | None = None,
) -> dict[str, Any]:
    # Keep recommendations inside the persona affinity graph whenever possible.
    # The previous ordering put affinity before exposure, which repeatedly chose
    # one perfect-match garment for an entire scene block.
    affinity_candidates = [item for item in candidates if float(item["record_template"]["persona_affinity"].get(persona, 0)) > 0]
    candidates = affinity_candidates or candidates
    season_candidates = [
        item for item in candidates
        if season in item["record_template"]["season_tags"] or "四季" in item["record_template"]["season_tags"]
    ]
    candidates = season_candidates or candidates
    recent = recent or Counter()
    return min(
        candidates,
        key=lambda item: (
            1 if recent[item["job_id"]] >= 2 else 0,
            recent[item["job_id"]],
            0 if scene in item["record_template"]["scene_tags"] else 1,
            usage[item["job_id"]],
            -float(item["record_template"]["persona_affinity"].get(persona, 0)),
            item["job_id"],
        ),
    )


def build_outfits(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    masters: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    usage: Counter[str] = Counter()
    for persona in PERSONAS:
        recent_outfits: list[set[str]] = []
        recent_variant_heroes: list[str] = []
        for index in range(30):
            scene, season = SCENE_QUOTA[index], SEASON_QUOTA[index]
            selected: list[dict[str, Any]] = []
            recent = Counter(item for outfit in recent_outfits[-9:] for item in outfit)
            for category in _master_composition(index):
                candidates = _eligible(jobs, persona, category, season, scene)
                chosen = _choose(candidates, persona, season, scene, usage, recent)
                usage[chosen["job_id"]] += 1
                selected.append(chosen)
            outfit_id = f"outfit_{persona.lower()}_master_{index + 1:02d}"
            garment_ids = [item["record_template"]["id"] for item in selected]
            slot_roles = {garment_ids[0]: "hero", **{item: "support" for item in garment_ids[1:-1]}, garment_ids[-1]: "accent"}
            tone, lightness, saturation, harmony = COLOR_RULES[persona]
            master = {
                "id": outfit_id, "kind": "master", "parent_outfit_id": None, "recipe_version": "2.0",
                "title": f"{persona} {scene} {index + 1:02d}", "description": f"{persona} 人格的{season}{scene}原创穿搭配方。",
                "primary_persona": persona, "secondary_personas": list(ADJACENT[persona]),
                "persona_affinity": {persona: 0.96, ADJACENT[persona][0]: 0.65, ADJACENT[persona][1]: 0.55},
                "regional_styles": [], "body_types": ["梨型", "倒三角型", "沙漏型", "矩型", "苹果型"],
                "scene_tags": [scene], "season_tags": [season], "weather_tags": ["晴", "室内"],
                "presentation": [PRESENTATION_QUOTA[index]], "intensity": INTENSITY_QUOTA[index], "formality": 4 if scene in {"通勤", "正式活动"} else 3,
                "garment_ids": garment_ids, "visible_slots": _master_composition(index), "layer_graph": [], "slot_roles": slot_roles,
                "replacement_rules": {"same_slot": True, "match_season": True, "match_scene": True, "max_formality_delta": 1, "preserve_color_harmony": True},
                "structure": {"visual_weight": "上下均衡", "waistline": "自然腰", "tummy_space": "合体不贴", "line_direction": "纵向"},
                "color": {"temperature": tone, "lightness": lightness, "saturation": saturation, "harmony": harmony, "palette": []},
                "recommendation_reasons": [f"呼应 {persona} 的廓形与材质偏好", f"适合{season}{scene}场景"],
                "assets": {"image_url": f"/static/selfit/assets/content_v2/{persona.lower()}/outfits/{outfit_id}.webp", "source_url": "", "width": 1200, "height": 1500, "alpha_verified": False, "rights_status": "owned"},
                "annotation": {"status": "unlabeled", "source": "designer", "confidence": 0.0, "review_notes": ["等待单品完成和平铺审核"]},
            }
            masters.append(master)
            recent_outfits.append(set(item["job_id"] for item in selected))
            variant_count = 2 if index < 15 else 1
            for variant_index in range(variant_count):
                variant = json.loads(json.dumps(master, ensure_ascii=False))
                variant["id"] = f"{outfit_id}_v{variant_index + 1}"
                variant["kind"] = "variant"
                variant["parent_outfit_id"] = outfit_id
                variant["title"] = master["title"] + f" · 替换 {variant_index + 1}"
                # A variant should read as a genuinely different recommendation,
                # not the same hero garment with a barely visible accessory swap.
                replacement_slot = 0
                original = selected[replacement_slot]
                candidates = [item for item in _eligible(jobs, persona, original["category"], season, scene) if item["record_template"]["id"] != original["record_template"]["id"]]
                if candidates:
                    replacement = _choose(
                        candidates,
                        persona,
                        season,
                        scene,
                        usage,
                        Counter(recent_variant_heroes[-9:]),
                    )
                    usage[replacement["job_id"]] += 1
                    variant["garment_ids"][replacement_slot] = replacement["record_template"]["id"]
                    recent_variant_heroes.append(replacement["job_id"])
                variant["slot_roles"] = {item: role for item, role in zip(variant["garment_ids"], master["slot_roles"].values(), strict=True)}
                variant["assets"]["image_url"] = f"/static/selfit/assets/content_v2/{persona.lower()}/outfits/{variant['id']}.webp"
                variants.append(variant)
    assert len(masters) == 480 and len(variants) == 720
    return masters, variants


def build() -> dict[str, Any]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    jobs = build_garment_jobs(catalog)
    masters, variants = build_outfits(jobs)
    return {
        "schemaVersion": "2.0", "contentVersion": "2026.09-expansion-plan-v2", "status": "production",
        "generatedAt": datetime.now(UTC).isoformat(),
        "targets": {"garments": 600, "masterOutfits": 480, "variantOutfits": 720, "recommendableOutfits": 1200},
        "garmentJobs": jobs, "masterOutfits": masters, "variantOutfits": variants,
    }


def _merge_progress(data: dict[str, Any], existing_path: Path) -> dict[str, Any]:
    """Regenerating quotas must not erase completed imagegen/QA work."""

    if not existing_path.exists():
        return data
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    old_jobs = {job.get("job_id"): job for job in existing.get("garmentJobs", [])}
    for job in data.get("garmentJobs", []):
        old = old_jobs.get(job.get("job_id"))
        if not old:
            continue
        if old.get("attempts"):
            job["attempts"] = old["attempts"]
            job["expected_raw_output"] = old["expected_raw_output"]
            job["expected_output"] = old["expected_output"]
            job["status"] = old.get("status", "planned")
            old_record = old.get("record_template") or {}
            job["record_template"]["assets"] = old_record.get("assets", job["record_template"]["assets"])
            job["record_template"]["production"] = old_record.get("production", job["record_template"]["production"])
            job["record_template"]["annotation"] = old_record.get("annotation", job["record_template"]["annotation"])
        if old.get("status") in {"generated", "rejected", "approved"}:
            job["status"] = old["status"]
            job["record_template"] = old.get("record_template", job["record_template"])
    for section in ("masterOutfits", "variantOutfits"):
        old_outfits = {item.get("id"): item for item in existing.get(section, [])}
        for outfit in data.get(section, []):
            old = old_outfits.get(outfit.get("id"))
            if old and record_fingerprint(old) == record_fingerprint(outfit) and (old.get("annotation") or {}).get("status") in {"designer_reviewed", "published"}:
                outfit["annotation"] = old["annotation"]
                if old.get("quality_review"):
                    outfit["quality_review"] = old["quality_review"]
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    args = parser.parse_args()
    data = _merge_progress(build(), args.plan)
    args.plan.parent.mkdir(parents=True, exist_ok=True)
    args.queue.parent.mkdir(parents=True, exist_ok=True)
    args.plan.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.queue.write_text("".join(json.dumps({key: job[key] for key in ("job_id", "persona", "category", "tier", "reference_ids", "status", "expected_raw_output", "expected_output", "prompt")}, ensure_ascii=False) + "\n" for job in data["garmentJobs"]), encoding="utf-8")
    print(json.dumps({"plan": str(args.plan), "queue": str(args.queue), **data["targets"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

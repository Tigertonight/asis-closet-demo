#!/usr/bin/env python3
"""Expand the 16-persona prompt catalog into one built-in imagegen job per asset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "app/static/selfit/data/content-generation-prompts.v1.json"
OUTPUT = ROOT / "docs/SELFIT_IMAGEGEN_PROMPT_QUEUE_P0.jsonl"


def _category(name: str) -> str:
    rules = (
        ("shoes", ("鞋", "靴")),
        ("bag", ("包", "手袋", "托特", "肩背", "腋下", "邮差")),
        ("bottom", ("裤",)),
        ("dress", ("连衣", "旗袍", "泡袖裙")),
        ("skirt", ("裙",)),
        ("outer", ("外套", "大衣", "风衣", "西装", "皮衣", "夹克", "斗篷", "开衫")),
        ("accessory", ("配饰", "帽", "围巾", "腰带")),
    )
    return next((category for category, terms in rules if any(term in name for term in terms)), "top")


def build() -> list[dict[str, Any]]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    template = catalog["assetTypes"]["garment_cutout"]["prompt"]
    jobs: list[dict[str, Any]] = []
    for code, profile in catalog["personas"].items():
        for index, signature in enumerate(profile["signature"], 1):
            category = _category(signature)
            description = f"{profile['name']}（{code}）人格的{signature}；廓形：{profile['silhouette']}；必须保持克制而可日常穿着"
            prompt = template.format(
                garment_description=description,
                palette=profile["palette"],
                materials=profile["materials"],
            ) + f"\nPersona-specific avoid: {profile['avoid']}"
            jobs.append({
                "job_id": f"p0_{code.lower()}_{index:02d}",
                "persona": code,
                "persona_name": profile["name"],
                "garment_name": signature,
                "category": category,
                "execution": "one built-in imagegen call",
                "status": "planned",
                "expected_output": f"app/static/selfit/assets/content_v2/{code.lower()}/garments/{code.lower()}-signature-{index:02d}-raw-v1.png",
                "prompt": prompt,
            })
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    jobs = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "jobs": len(jobs), "personas": len({job['persona'] for job in jobs})}, ensure_ascii=False))


if __name__ == "__main__":
    main()

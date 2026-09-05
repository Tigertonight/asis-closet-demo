"""Record non-blind visual candidate judgments for P0 gap recipes.

This is staging evidence only. It is explicitly not four-gate editorial review
and not independent persona blind review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.recommendation_visual import asset_sha
from app.selfit_content_quality import record_fingerprint

JUDGMENTS = {
    "p0-gap-01": [
        ("reject", None, "不对称破边上衣的 WABI/VOID 证据强于 FILM，人格方向不通过。"),
        ("ai_candidate", ("iced", "skirt"), "斜向抽褶冰蓝背心为唯一主视觉，炭灰窄裙、乐福鞋与托特包都保持冷静线条，达到日常轻探索。"),
        ("ai_candidate", ("wabi", "pants"), "手作拼片上衣集中肌理和不对称证据，锥形裤与低饱和配件收敛，是可日常化的 WABI 轻探索。"),
        ("reject", None, "主裙体积和层片过强，更接近主题化造型，不符合 everyday_with_statement。"),
    ],
    "p0-gap-02": [
        ("ai_candidate", ("film", "pants"), "做旧牛仔束腰上衣提供明确胶片复古证据，宽裤与素色鞋包不抢焦点，轻探索且可日常。"),
        ("ai_candidate", ("wabi", "skirt"), "低饱和亚麻感不对称上衣为唯一主视觉，素色窄裙和简洁配件保留日常性。"),
    ],
}


def observations(persona: str, structure: str, evidence: str) -> dict:
    return {
        "axes": {}, "expression": "explore", "formality": "smart_casual", "layering": 1,
        "persona_scores": {persona: .9}, "scenes": ["daily", "commute"], "seasons": ["autumn"],
        "structure": structure, "wearability": "everyday_with_statement",
        "main_visual_slots": ["top", structure], "main_colors": [], "conflicts": None,
        "silhouette": "single_focal_daily_exploration", "color_relation": "low_competition_supports",
        "persona_evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite visual review evidence")
    rendered = json.loads(args.rendered.read_text())
    batch_id = rendered.get("batch_id")
    judgments = JUDGMENTS.get(batch_id)
    if judgments is None or len(judgments) != len(rendered.get("entries") or []):
        raise ValueError("No complete bounded judgment set for this batch")
    entries = []
    for entry, (status, accepted, evidence) in zip(rendered["entries"], judgments):
        record = entry["new_record"]
        row = {
            "outfit_id": record["id"], "status": status,
            "record_fingerprint": record_fingerprint(record),
            "asset_sha256": asset_sha(record["assets"]["image_url"]),
            "image_url": record["assets"]["image_url"],
            "source_kind": "codex_visual_review", "evidence": evidence,
            "model": "current_codex_session", "prompt_version": f"{batch_id}-visual-v1",
            "review_level": "individual_whole_image_judgment",
            "evidence_scope": "nonblind visual candidate only; not editorial or independent blind review",
        }
        if accepted:
            row.update({"observations": observations(*accepted, evidence), "confidence": .86})
        entries.append(row)
    result = {
        "schema_version": 1,
        "version": f"{batch_id}-visual-review-v1",
        "source_rendered_version": rendered["version"],
        "independent_blind_review": False,
        "four_gate_editorial_review": False,
        "entries": entries,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"accepted": sum(r["status"] == "ai_candidate" for r in entries),
                      "rejected": sum(r["status"] == "reject" for r in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

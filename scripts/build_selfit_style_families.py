"""Seed conservative, revision-bound families from the recorded visual audit."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool
from app.selfit_content_quality import record_fingerprint


def main():
    target = ROOT / "app/data/garment-style-families.v1.json"
    if target.exists():
        raise SystemExit("Registry exists; edit reviewed decisions explicitly instead of overwriting")
    records = {g["id"]: g for g in selfit_content_pool().garments}
    pairs = [
        ("navy-belted-pleated-skirt", "garment_heir_skirt_0435", "garment_heir_skirt_0579", "藏蓝腰带百褶裙：长度、褶裥与腰部细节高度相似"),
        ("beige-rolled-sleeve-shirt", "garment_ease_top_0324", "garment_ease_top_0564", "米色翻领卷袖衬衫：口袋、袖长、轮廓高度相似"),
        ("pale-blue-high-waist-trousers", "garment_iced_bottom_0402", "garment_iced_bottom_0418", "浅蓝高腰长裤：宽度略有变化，缩略图体感相近"),
    ]
    families = [{
        "id": "style-family:" + name, "status": "visual_reviewed",
        "reviewer": "codex-nonblind-visual-audit-20260903",
        "independent_persona_review": False,
        "evidence": "docs/SELFIT_RECOMMENDATION_PERSONA_DIVERSITY_AUDIT_20260903.md",
        "rationale": reason,
        "members": {gid: record_fingerprint(records[gid]) for gid in (a, b)},
    } for name, a, b, reason in pairs]
    registry = {
        "schema_version": 1,
        "policy": "Same style family is an exposure constraint, not an asset deletion or persona approval. Unassigned garments remain singleton families. Color alone never merges styles.",
        "dimensions": ["category", "neckline", "sleeve", "length", "volume", "waist", "construction", "pattern", "material", "color"],
        "unknown_dimensions": "Do not infer actual cut/material from production prompts; keep unreviewed fields unknown.",
        "candidate_queue": {"source": "docs/audits/20260903-recommendation-similarity/audit-data.json", "field": "garment_similarity.joint_pairs", "status": "pending_visual_review", "automatic_merge": False},
        "families": families,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    print(f"Created {target}: 3 reviewed families / 6 members; other garments remain singleton")


if __name__ == "__main__":
    main()

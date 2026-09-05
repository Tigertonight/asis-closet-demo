"""Offline independent persona review. Never auto-approves the live catalog.

Build gives the reviewer ONLY reviewer.zip. Examiner keys remain separate.
Grade checks declarations/revision evidence, not the reviewer's real identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import _published_catalog_outfits, selfit_content_pool
from app.selfit_content_quality import record_fingerprint

PRODUCER = "codex-selfit-content-team"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def select_anchors(outfits):
    selected = []
    for persona in sorted({o["primary_persona"] for o in outfits}):
        used_parents, used_heroes = set(), set()
        for intensity, count in (("entry", 4), ("signature", 4), ("experimental", 2)):
            candidates = [o for o in outfits if o["primary_persona"] == persona and o.get("intensity") == intensity]
            for _ in range(count):
                available = [o for o in candidates if (o.get("parent_outfit_id") or o["id"]) not in used_parents]
                if not available:
                    raise ValueError(f"Insufficient distinct anchors: {persona}/{intensity}")
                def hero(o):
                    return next((g for g, role in o.get("slot_roles", {}).items() if role == "hero"), o["garment_ids"][0])
                # Sample across recipes/hero items, not score or existing approval.
                picked = min(available, key=lambda o: (hero(o) in used_heroes, hashlib.sha256(o["id"].encode()).hexdigest()))
                selected.append(picked)
                used_parents.add(picked.get("parent_outfit_id") or picked["id"])
                used_heroes.add(hero(picked))
    return selected


def build(output):
    if output.exists():
        raise ValueError("Use a new output directory; never overwrite review evidence")
    pool = selfit_content_pool()
    garments = {g["id"]: g for g in pool.garments}
    selected = select_anchors(pool.outfits)
    if len(selected) != 160:
        raise ValueError("Expected 16 personas × 10 anchors")
    random.Random(20260903).shuffle(selected)
    reviewer = output / "reviewer"
    reviewer.mkdir(parents=True)
    templates = json.loads((ROOT / "app/static/selfit/data/personality-report-templates.v1.json").read_text())["types"]
    save(reviewer / "persona-rubric.json", {k: {field: t[field] for field in ("metadata", "keywords", "summary")} for k, t in templates.items()})
    covers = {o["outfit_id"]: o["cover_path"] for o in _published_catalog_outfits()}
    keys, answers = {}, []
    sheet = None
    for n, outfit in enumerate(selected):
        token = f"look-{n+1:03d}"
        path = ROOT / "app" / covers[outfit["id"]].lstrip("/")
        with Image.open(path) as source:
            # Re-encode: no source filenames, EXIF or embedded persona metadata.
            image = ImageOps.contain(source.convert("RGB"), (600, 750))
            image.save(reviewer / f"{token}.jpg", quality=95)
        if n % 20 == 0:
            sheet = Image.new("RGB", (1200, 1360), "white")
        thumb = ImageOps.contain(image, (230, 300))
        x, y = (n % 5) * 240, ((n % 20) // 5) * 340
        sheet.paste(thumb, (x + (240-thumb.width)//2, y+25))
        ImageDraw.Draw(sheet).text((x+10, y+8), token, fill="black")
        if n % 20 == 19:
            sheet.save(reviewer / f"sheet-{n//20+1:02d}.jpg", quality=92)
        keys[token] = {
            "outfit_id": outfit["id"], "primary_persona": outfit["primary_persona"].lower(),
            "intensity": outfit["intensity"], "record_fingerprint": record_fingerprint(outfit),
            "cover_path": str(path.relative_to(ROOT)), "cover_sha256": digest(path),
            "review_image_sha256": digest(reviewer / f"{token}.jpg"),
            "garment_fingerprints": {gid: record_fingerprint(garments[gid]) for gid in outfit["garment_ids"]},
        }
        answers.append({"token": token, "top1": "", "top2": "", "reason": "", "issues": [], "verdict": "pending"})
    instructions = """# 独立人格复核

只交付本目录 / reviewer.zip，不给审核者 examiner-key.json。
本包包含 160 套匿名穿搭；先阅读 persona-rubric.json，逐套查看大图。
不要查询源文件名、原人格标签、推荐分或生产提示词；按视觉判断 Top-1 / Top-2。
reason 需写出廓形、材质观感、色彩、比例、场景等证据；不确定也必须如实说明。
verdict 填 accept / reject / uncertain，issues 填搭配冲突、轮廓雷同、人格弱等问题。
answers.json 填审核者姓名/身份标识；只有未参与这些内容的生产/标注且未看到答案者才能声明 independent=true、labels_hidden=true。
本工具只记录独立性声明，不认证真实身份，不能用同一生产者的自审冒充盲审。
Top-1 ≥70%、Top-2 ≥90% 是待验证目标，不是本包的已取得成绩。
样本审查不代表 1,169 套全量审查；结果回收后逐套处置，禁止按总分自动批准整个池。
"""
    (reviewer / "README.md").write_text(instructions)
    package_id = hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()
    save(output / "examiner-key.json", {"package_id": package_id, "producer": PRODUCER, "keys": keys})
    save(reviewer / "answers.json", {"package_id": package_id, "reviewer": "", "independent": False, "labels_hidden": False, "answers": answers})
    with zipfile.ZipFile(output / "reviewer.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(reviewer.iterdir()):
            archive.write(path, path.name)
    save(output / "status.json", {"status": "pending_independent_review", "samples": 160, "personas": 16, "reviewed": 0, "top1_accuracy": None, "top2_accuracy": None})
    print(f"Created {output}/reviewer.zip; 160 samples, 0 reviewed. Keep examiner key separate.")


def grade(key, answers, outfits, garments, root=ROOT):
    if (answers.get("package_id") != key["package_id"] or not str(answers.get("reviewer") or "").strip()
            or answers.get("reviewer") == key["producer"]
            or answers.get("independent") is not True or answers.get("labels_hidden") is not True):
        raise ValueError("Matching package and declared independent, blinded reviewer required")
    records = key["keys"]
    rows = answers.get("answers", [])
    if len({a["token"] for a in rows}) != len(rows) or {a["token"] for a in rows} != set(records):
        raise ValueError("Every token must appear exactly once")
    codes = {k["primary_persona"] for k in records.values()}
    scores, decisions = {}, []
    for row in rows:
        expected = records[row["token"]]
        oid = expected["outfit_id"]
        if oid not in outfits or record_fingerprint(outfits[oid]) != expected["record_fingerprint"]:
            raise ValueError(f"Stale outfit: {oid}")
        if digest(root / expected["cover_path"]) != expected["cover_sha256"]:
            raise ValueError(f"Stale image: {oid}")
        if any(gid not in garments or record_fingerprint(garments[gid]) != fp for gid, fp in expected["garment_fingerprints"].items()):
            raise ValueError(f"Stale garment: {oid}")
        if (row.get("top1") not in codes or row.get("top2") not in codes or row["top1"] == row["top2"]
                or not str(row.get("reason") or "").strip() or row.get("verdict") not in {"accept", "reject", "uncertain"}
                or not isinstance(row.get("issues"), list)):
            raise ValueError(f"Incomplete review: {row['token']}")
        code = expected["primary_persona"]
        counts = scores.setdefault(code, Counter())
        counts["samples"] += 1
        counts["top1_hits"] += row["top1"] == code
        counts["top2_hits"] += code in (row["top1"], row["top2"])
        counts["rejected_or_uncertain"] += row["verdict"] != "accept"
        decisions.append({**row, "outfit_id": oid, "expected_persona": code, "record_fingerprint": expected["record_fingerprint"]})
    totals = sum(scores.values(), Counter())
    return {"status": "independent_review_recorded_pending_editorial_decisions", "package_id": key["package_id"],
            "reviewer": answers["reviewer"],
            "identity_verification": "declaration_only", "catalog_mutated": False,
            "independent": answers["independent"], "labels_hidden": answers["labels_hidden"],
            "samples": totals["samples"], "top1_accuracy": totals["top1_hits"]/totals["samples"],
            "top2_accuracy": totals["top2_hits"]/totals["samples"], "by_persona": scores,
            "thresholds": {"overall_top1": .70, "overall_top2": .90, "persona_top1": .60, "persona_top2": .80},
            "decisions": decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("build").add_argument("output", type=Path)
    g = sub.add_parser("grade")
    for arg in ("key", "answers", "output"):
        g.add_argument(arg, type=Path)
    args = parser.parse_args()
    if args.action == "build":
        build(args.output)
    else:
        if args.output.exists():
            raise ValueError("Use a new result path")
        pool = selfit_content_pool()
        result = grade(json.loads(args.key.read_text()), json.loads(args.answers.read_text()),
                       {o["id"]: o for o in pool.outfits}, {g["id"]: g for g in pool.garments})
        save(args.output, result)


if __name__ == "__main__":
    main()

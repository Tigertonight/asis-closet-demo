"""Revision-bound, label-free component sheets for native family comparison.

Connected components are a browsing aid, NOT a style family decision. Images
are original RGBA assets on white, contain-fitted without stretching/cropping.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def components(pairs):
    graph = defaultdict(set)
    for pair in pairs:
        graph[pair["left"]].add(pair["right"])
        graph[pair["right"]].add(pair["left"])
    seen, result = set(), []
    for gid in sorted(graph):
        if gid in seen:
            continue
        queue, group = [gid], []
        seen.add(gid)
        while queue:
            current = queue.pop()
            group.append(current)
            for other in sorted(graph[current] - seen):
                seen.add(other)
                queue.append(other)
        result.append(group)
    return sorted(result, key=lambda group: (-len(group), min(group)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/audits/20260903-personal-home-visual/family-review")
    args = parser.parse_args()
    if (args.output / "manifest.json").exists():
        raise SystemExit("Evidence already exists; do not overwrite")
    audit = ROOT / "docs/audits/20260903-personal-home-visual"
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    pairs = json.loads((ROOT / "docs/audits/20260903-recommendation-similarity/audit-data.json").read_text())["garment_similarity"]["joint_pairs"]
    rows, pages, small = [], [], []
    for number, group in enumerate(components(pairs), 1):
        members = [{"garment_id": gid, "component": f"c{number:02d}", **{k: visual["garments"][gid][k]
                   for k in ("token", "image_url", "asset_sha256", "record_fingerprint")}}
                   for gid in sorted(group, key=lambda g: visual["garments"][g]["token"])]
        if len(group) > 9:
            pages.append(members)
        else:
            if len(small) + len(members) > 24:
                pages.append(small)
                small = []
            small.extend(members)
        rows.extend(members)
    if small:
        pages.append(small)
    args.output.mkdir(parents=True, exist_ok=True)
    for number, members in enumerate(pages, 1):
        width, height, columns = 240, 288, 6
        sheet = Image.new("RGB", (width * columns, height * ((len(members) + columns - 1) // columns)), "#f8f8f8")
        draw = ImageDraw.Draw(sheet)
        name = f"family-components-{number:02d}.jpg"
        for index, member in enumerate(members):
            path = ROOT / "app" / member["image_url"].lstrip("/")
            assert hashlib.sha256(path.read_bytes()).hexdigest() == member["asset_sha256"]
            x, y = (index % columns) * width, (index // columns) * height
            draw.rectangle((x + 3, y + 24, x + width - 3, y + height - 4), fill="white")
            with Image.open(path) as original:
                image = original.convert("RGBA")
                image.thumbnail((width - 12, height - 32))
                sheet.paste(image, (x + (width - image.width) // 2, y + 26 + (height - 32 - image.height) // 2), image)
            draw.text((x + 7, y + 5), f"{member['component']} | {member['token']}", fill="black", font=ImageFont.load_default())
            member["sheet"], member["position"] = name, index + 1
        sheet.save(args.output / name, quality=95)
    data = {"schema_version": 1, "visual_version": visual["version"], "pairs": pairs, "members": rows,
            "pair_count": len(pairs), "component_count": len(components(pairs)), "sheet_count": len(pages),
            "scope": "Machine-connected candidates only; connectedness never approves same-family membership."}
    (args.output / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: data[k] for k in ("pair_count", "component_count", "sheet_count")}))


if __name__ == "__main__":
    main()

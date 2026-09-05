"""Build immutable labeled sheets for native review of unused main garments."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    ledger = json.loads((ROOT / "docs/audits/20260904-aw-supply/repair-ledger.initial.json").read_text())
    pool = json.loads((ROOT / "app/static/selfit/data/content-pool.v2.published.json").read_text())
    by_id = {row["id"]: row for row in pool["garments"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if list(args.output_dir.glob("idle-main-*.jpg")):
        raise SystemExit("Review sheets already exist; refusing overwrite")
    font = ImageFont.load_default(size=22)
    rows = ledger["unused_main_garments"]
    manifest = []
    for start in range(0, len(rows), 12):
        batch = rows[start:start + 12]
        sheet = Image.new("RGB", (1600, 1950), "#f7f4f3")
        draw = ImageDraw.Draw(sheet)
        for index, record in enumerate(batch):
            col, row = index % 4, index // 4
            x, y = 20 + col * 395, 20 + row * 640
            garment = by_id[record["garment_id"]]
            source = ROOT / "app" / garment["assets"]["image_url"].lstrip("/")
            image = Image.open(source).convert("RGBA")
            bbox = image.getchannel("A").getbbox()
            if bbox:
                image = image.crop(bbox)
            image.thumbnail((355, 520), Image.Resampling.LANCZOS)
            sheet.paste(Image.new("RGB", image.size, "white"), (x + (355-image.width)//2, y+42))
            sheet.paste(image, (x + (355-image.width)//2, y+42), image)
            draw.text((x, y), f"{start+index+1:02d} {record['token']} {record['category']}", fill="#202020", font=font)
            draw.text((x, y+575), "/".join(record["visual_personas"]), fill="#8f1230", font=font)
        path = args.output_dir / f"idle-main-{start//12+1}.jpg"
        sheet.save(path, quality=94)
        manifest.append({"sheet": path.name, "tokens": [r["token"] for r in batch]})
    (args.output_dir / "manifest.json").write_text(json.dumps({"source_ledger_version":ledger["version"],"sheets":manifest}, indent=2))


if __name__ == "__main__":
    main()

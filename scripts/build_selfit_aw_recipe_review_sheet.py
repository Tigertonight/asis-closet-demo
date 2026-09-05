"""Build immutable six-up sheets from an AW rendered recipe manifest."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if list(args.output_dir.glob("recipes-*.jpg")):
        raise SystemExit("Review sheets already exist; refusing overwrite")
    font = ImageFont.load_default(size=20)
    sheets = []
    for start in range(0, len(data["entries"]), 6):
        batch = data["entries"][start:start+6]
        sheet = Image.new("RGB", (1500, 2000), "#f7f4f3")
        draw = ImageDraw.Draw(sheet)
        for pos, entry in enumerate(batch):
            col, row = pos % 3, pos // 3
            x, y = 20 + col*490, 20 + row*980
            record = entry["new_record"]
            path = ROOT / "app" / record["assets"]["image_url"].lstrip("/")
            image = Image.open(path).convert("RGB")
            image.thumbnail((450, 860), Image.Resampling.LANCZOS)
            sheet.paste(image, (x+(450-image.width)//2, y+45))
            token = entry.get("hero") or entry.get("source_token") or record.get("id")
            draw.text((x, y), f"{start+pos+1:02d} {token} {record['primary_persona']}", fill="#202020", font=font)
        target = args.output_dir / f"recipes-{start//6+1}.jpg"
        sheet.save(target, quality=94)
        sheets.append({"sheet":target.name,"tokens":[e.get("hero") or e.get("source_token") for e in batch]})
    source_version = data.get("version") or data.get("batch_id")
    (args.output_dir/"manifest.json").write_text(json.dumps({"source_version":source_version,"sheets":sheets},indent=2)+"\n")


if __name__ == "__main__":
    main()

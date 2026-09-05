"""Build derived layered covers without modifying published recipes or QA decisions."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.outfit_layered_layout import layered_preview_url, render_layered_preview


def main():
    pool = json.loads((ROOT / "app/static/selfit/data/content-pool.v2.published.json").read_text())
    garments = {item["id"]: item for item in pool["garments"]}
    rendered = 0
    for outfit in pool["outfits"]:
        items = [garments[key] for key in outfit["garment_ids"]]
        if layered_preview_url(items):
            render_layered_preview(items, ROOT)
            rendered += 1
            if rendered % 24 == 0:
                print(f"Rendered {rendered} layered previews", flush=True)
    print(f"Completed: {rendered}. Source pool unchanged.")


if __name__ == "__main__":
    main()

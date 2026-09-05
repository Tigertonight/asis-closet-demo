"""Offline, resumable rebuild of all catalog covers; never edit source pools."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.outfit_layout import outfit_preview_url, render_outfit_preview


def main():
    path = ROOT / "app/static/selfit/data/content-pool.v2.published.json"
    original = path.read_bytes()
    pool = json.loads(original)
    garments = {g["id"]: g for g in pool["garments"]}
    recipes = {outfit_preview_url(items): items for o in pool["outfits"]
               for items in [[garments[key] for key in o["garment_ids"]]]}

    def render(pair):
        url, items = pair
        output = ROOT / "app" / url.lstrip("/")
        if not output.is_file() or not output.with_suffix(".qa.json").is_file():
            render_outfit_preview(items, ROOT)

    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, _ in enumerate(executor.map(render, recipes.items()), 1):
            if i % 100 == 0:
                print(f"Verified {i}/{len(recipes)} covers", flush=True)
    assert path.read_bytes() == original, "Source pool changed during build"
    print(json.dumps({"outfits": len(pool["outfits"]), "covers": len(recipes), "source_sha256": hashlib.sha256(original).hexdigest()}), flush=True)


if __name__ == "__main__":
    main()

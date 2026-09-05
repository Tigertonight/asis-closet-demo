import hashlib
import itertools
import json
from pathlib import Path

import pytest
from PIL import Image

from app import closet
from app.outfit_layout import CANVAS, LAYOUT_VERSION, outfit_box, outfit_preview_url, render_outfit_preview
from tests.test_layered_outfit_layout import intersects, make_garments


@pytest.mark.parametrize("main", [["top", "bottom"], ["top", "skirt"], ["dress"], ["outer", "bottom"], ["outer", "top", "bottom"], ["outer", "dress"]])
def test_all_silhouettes_share_safe_nonoverlapping_accessory_rail(main):
    slots = [*main, "hat", "scarf", "bag", "shoes", "accessory_1", "accessory_2", "socks"]
    boxes = [outfit_box(slot, slots) for slot in slots]
    assert all(not intersects(a, b) for a, b in itertools.combinations(boxes, 2))
    assert all(x1 >= 66 and y1 >= 82 and x2 <= 1134 and y2 <= 1418 for x1, y1, x2, y2 in boxes)
    for accessory in ["hat", "bag", "shoes", "scarf"]:
        assert outfit_box(accessory, slots) == outfit_box(accessory, ["dress"])


@pytest.mark.parametrize("main", [["top", "bottom"], ["dress"], ["outer", "top", "bottom"]])
def test_catalog_and_wardrobe_share_layout(monkeypatch, tmp_path, main):
    garments = make_garments(tmp_path, [*main, "bag", "shoes"])
    report = render_outfit_preview(garments, tmp_path)
    items = [{"item_id": g["id"], "category": "top" if g["category"] == "outer" else g["category"],
              "attributes": {"style_tags": ["outer"] if g["category"] == "outer" else []},
              "assets": {"cutout_path": g["assets"]["image_url"]}} for g in garments]
    monkeypatch.setattr(closet, "_closet_disk_path", lambda url: tmp_path / "app" / url.lstrip("/"))
    monkeypatch.setattr(closet, "_outfit_dir", lambda: tmp_path / "private")
    private = closet._build_outfit_cover("own", items)
    by_slot = {p["slot"]: p["box"] for p in report["placements"]}
    for p in private["layout_slots"]:
        b = p["box"]
        actual = [b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]]
        assert all(abs(a - b) <= 1 for a, b in zip(actual, by_slot[p["slot"]]))
    assert private["layout_version"] == LAYOUT_VERSION
    assert private["path"].is_relative_to(tmp_path / "private")


def test_every_published_recipe_has_complete_unified_cover():
    root = Path(__file__).resolve().parents[1]
    path = root / "app/static/selfit/data/content-pool.v2.published.json"
    raw = path.read_bytes()
    pool = json.loads(raw)
    garments = {g["id"]: g for g in pool["garments"]}
    assert len(pool["outfits"]) == 1200
    checked = set()
    for outfit in pool["outfits"]:
        url = outfit_preview_url([garments[key] for key in outfit["garment_ids"]])
        asset = root / "app" / url.lstrip("/")
        report = json.loads(asset.with_suffix(".qa.json").read_text())
        assert report["layout_version"] == LAYOUT_VERSION
        assert sorted(p["garment_id"] for p in report["placements"]) == sorted(outfit["garment_ids"])
        assert len({p["garment_id"] for p in report["placements"]}) == len(outfit["garment_ids"])
        boxes = [p["box"] for p in report["placements"]]
        assert all(not intersects(a, b) for a, b in itertools.combinations(boxes, 2))
        assert all(x1 >= 66 and y1 >= 82 and x2 <= 1134 and y2 <= 1418 for x1, y1, x2, y2 in boxes)
        if url not in checked:
            with Image.open(asset) as image:
                assert image.size == CANVAS
            checked.add(url)
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(raw).digest()


def test_flatlay_css_has_definite_image_bounds_and_no_zoom():
    css = (Path(closet.__file__).parent / "static/selfit-app/app.css").read_text()
    assert 'scale(1.06)' not in css
    frame = css.split('.outfit-canvas > img {', 1)[1].split('}', 1)[0]
    assert 'position: absolute' in frame and 'object-fit: contain' in frame
    assert 'height: 100%' in frame and 'transform: none' in frame

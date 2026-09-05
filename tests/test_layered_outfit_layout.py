import copy
import itertools
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app import closet
from app.outfit_layered_layout import LAYERED_LAYOUT_VERSION, layered_box, layered_preview_url, render_layered_preview
from app.outfit_layout import LAYOUT_VERSION, render_outfit_preview


def intersects(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


@pytest.mark.parametrize("main", [["top", "bottom"], ["top", "skirt"], ["dress"]])
def test_layered_regions_are_disjoint_and_inside_safe_margin(main):
    slots = ["outer", *main, "hat", "scarf", "bag", "shoes", "socks", "accessory_1", "accessory_2"]
    boxes = [layered_box(slot) for slot in slots]
    assert all(not intersects(a, b) for a, b in itertools.combinations(boxes, 2))
    assert all(x1 >= 66 and y1 >= 82 and x2 <= 1134 and y2 <= 1418 for x1, y1, x2, y2 in boxes)


def make_garments(root, categories):
    garments = []
    for index, category in enumerate(categories):
        url = f"/static/test-{index}.png"
        path = root / "app" / url.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (1200, 1200))
        ImageDraw.Draw(image).rectangle((400, 100, 800, 1100), fill=(40 + index * 20, 30, 60, 255))
        image.save(path)
        garments.append({"id": str(index), "category": category, "assets": {"image_url": url, "sha256": str(index)}})
    return garments


def test_layered_preview_crops_padding_not_subject_and_preserves_sources(tmp_path):
    garments = make_garments(tmp_path, ["top", "bottom", "outer", "shoes", "bag"])
    original = copy.deepcopy(garments)
    source_bytes = [(tmp_path / "app" / g["assets"]["image_url"].lstrip("/")).read_bytes() for g in garments]
    report = render_layered_preview(garments, tmp_path)
    boxes = [p["box"] for p in report["placements"]]
    assert report["layout_version"] == LAYERED_LAYOUT_VERSION
    assert all(not intersects(a, b) for a, b in itertools.combinations(boxes, 2))
    assert [p["garment_id"] for p in report["placements"]] == [g["id"] for g in garments]
    assert garments == original
    assert source_bytes == [(tmp_path / "app" / g["assets"]["image_url"].lstrip("/")).read_bytes() for g in garments]
    assert Image.open(tmp_path / "app" / report["image_url"].lstrip("/")).size == (1200, 1500)
    # Changing an asset revision or slot invalidates the derived URL; input order does not.
    assert layered_preview_url(list(reversed(garments))) == layered_preview_url(garments)
    changed = copy.deepcopy(garments)
    changed[0]["assets"]["sha256"] = "changed"
    assert layered_preview_url(changed) != layered_preview_url(garments)


@pytest.mark.parametrize("inner", [["top", "bottom"], ["dress"]])
def test_personal_layered_cover_keeps_outer_and_inner(monkeypatch, tmp_path, inner):
    garments = make_garments(tmp_path, ["outer", *inner, "shoes", "bag"])
    items = [{"item_id": g["id"], "category": "top" if g["category"] == "outer" else g["category"],
              "attributes": {"style_tags": ["outer"] if g["category"] == "outer" else []},
              "assets": {"cutout_path": g["assets"]["image_url"]}} for g in garments]
    monkeypatch.setattr(closet, "_closet_disk_path", lambda url: tmp_path / "app" / url.lstrip("/"))
    monkeypatch.setattr(closet, "_outfit_dir", lambda: tmp_path / "outfits")
    result = closet._build_outfit_cover("test-layered", items)
    assert result["layout_version"] == LAYOUT_VERSION
    assert len(result["layout_slots"]) == len(items)
    assert not result["overflow_items"]
    boxes = [[p["box"]["x"], p["box"]["y"], p["box"]["x"] + p["box"]["width"], p["box"]["y"] + p["box"]["height"]] for p in result["layout_slots"]]
    assert all(not intersects(a, b) for a, b in itertools.combinations(boxes, 2))


def test_detail_feedback_has_only_two_accessible_icon_buttons():
    source = Path(closet.__file__).read_text()
    fragment = source.split('<div id="detailFeedbackActions"', 1)[1].split('</div>', 1)[0]
    assert fragment.count('<button ') == 2
    assert fragment.count('aria-pressed="false"') == 2
    assert fragment.count('<svg ') == 2
    assert 'detailWornBtn' not in source


@pytest.mark.parametrize("categories", [["outer", "top", "top"], ["outer", "dress", "top"], ["outer", "top", "bottom", "skirt"]])
def test_conflicting_layered_slots_fail_instead_of_hiding_a_piece(tmp_path, categories):
    with pytest.raises(ValueError, match="Conflicting slot"):
        render_layered_preview(make_garments(tmp_path, categories), tmp_path)


def test_catalog_prefers_prebuilt_layered_cover_and_falls_back(monkeypatch, tmp_path):
    from types import SimpleNamespace
    garments = make_garments(tmp_path, ["top", "bottom", "outer", "shoes", "bag"])
    for garment in garments:
        garment["assets"]["rights_status"] = "owned"
    outfit = {"id": "layered", "garment_ids": [g["id"] for g in garments], "annotation": {"status": "published"}, "assets": {"image_url": "/static/original.webp"}}
    pool = SimpleNamespace(metadata={"status": "published"}, garments=garments, outfits=[outfit], all_outfits=[outfit])
    monkeypatch.setattr(closet, "selfit_content_pool", lambda: pool)
    monkeypatch.setattr(closet, "ROOT_DIR", tmp_path)
    assert closet._published_catalog_outfits()[0]["cover_path"] == "/static/original.webp"
    report = render_outfit_preview(garments, tmp_path)
    adapted = closet._published_catalog_outfits()[0]
    assert adapted["cover_path"] == report["image_url"]
    assert adapted["layout_snapshot_path"] == report["image_url"]
    assert adapted["layout_version"] == LAYOUT_VERSION
    assert outfit["assets"]["image_url"] == "/static/original.webp"


@pytest.mark.parametrize("main", [["top", "bottom"], ["dress"], ["top", "bottom", "outer"]])
def test_future_production_uses_same_nonoverlapping_layout(monkeypatch, tmp_path, main):
    from scripts import build_selfit_outfit_flatlay as production
    garments = make_garments(tmp_path, [*main, "shoes", "bag"])
    plan = {"garmentJobs": [{"record_template": g} for g in garments], "masterOutfits": [{
        "id": "future-layered", "garment_ids": [g["id"] for g in garments],
        "assets": {"image_url": "/static/future-layered.webp"},
    }]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(production, "ROOT", tmp_path)
    result = production.build_from_plan(path)
    derived = render_outfit_preview(garments, tmp_path)
    # Both paths share the same safe boxes and alpha-aware fitting.
    with Image.open(result["completed"][0]["output"]) as a, Image.open(tmp_path / "app" / derived["image_url"].lstrip("/")) as b:
        assert a.size == b.size
        for x, y in [(70, 80), (430, 400), (620, 650), (830, 800)]:
            assert all(abs(u - v) <= 5 for u, v in zip(a.getpixel((x, y)), b.getpixel((x, y))))

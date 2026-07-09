from __future__ import annotations

import io
import itertools
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.closet as closet
import app.auth as auth
import app.storage as storage
import app.tryon as tryon
from app.main import app


_phone_counter = itertools.count(1000)


def _auth_client(phone: str | None = None) -> TestClient:
    phone = phone or f"+8613800{next(_phone_counter):06d}"
    client = TestClient(app)
    start = client.post("/auth/phone/start", json={"phone": phone}).json()
    token = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60, 105)
    return image


def _synthetic_top_image_with_color(color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = color
    return image


def _create_closet_item(client: TestClient, name: str, category: str, color: tuple[int, int, int]) -> dict:
    created = client.post(
        "/closet/import/upload",
        files=[("images", (name, _png_bytes(_synthetic_top_image_with_color(color)), "image/png"))],
    ).json()["items"][0]
    if category != "top":
        patched = client.patch(f"/closet/items/{created['item_id']}", json={"category": category})
        assert patched.status_code == 200
        return patched.json()
    return created


def _use_tmp_closet(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setattr(closet, "CLOSET_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(closet, "CLOSET_SOURCE_DIR", tmp_path / "sources")
    monkeypatch.setattr(closet, "CLOSET_ITEM_DIR", tmp_path / "items")
    monkeypatch.setattr(closet, "CLOSET_MANIFEST_PATH", tmp_path / "closet_manifest.json")
    monkeypatch.setattr(closet, "OUTFIT_DIR", tmp_path / "outfits")
    monkeypatch.setattr(closet, "OUTFIT_MANIFEST_PATH", tmp_path / "outfits_manifest.json")
    monkeypatch.setattr(closet, "TRYON_RECORD_DIR", tmp_path / "tryon_records")
    monkeypatch.setattr(closet, "TRYON_RECORDS_MANIFEST_PATH", tmp_path / "tryon_records_manifest.json")


def test_closet_upload_import_creates_manifest_item(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["summary"]["created"] == 1
    item = data["items"][0]
    assert item["category"] == "top"
    assert item["assets"]["cutout_path"].startswith("/user-assets/closet/")
    assert item["assets"]["preview_path"].startswith("/user-assets/closet/")
    preview_path = closet._closet_disk_path(item["assets"]["preview_path"])
    assert preview_path is not None
    assert Image.open(preview_path).size == (900, 900)
    assert (tmp_path / "closet_manifest.json").exists()


def test_closet_cutout_quality_flags_sparse_reference(tmp_path: Path) -> None:
    cutout = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    for y in range(150, 170):
        for x in range(150, 170):
            cutout.putpixel((x, y), (220, 60, 105, 255))
    cutout_path = tmp_path / "sparse_cutout.png"
    cutout.save(cutout_path)

    quality = closet._closet_cutout_quality("top", cutout_path, 0.78, ["semantic_segmentation_mask"])

    assert quality["status"] in {"review", "rejected"}
    assert "foreground_too_sparse" in quality["reasons"]


def test_closet_upload_rejects_empty_image(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("empty.png", b"", "image/png"))],
    )

    assert response.status_code == 400
    assert "没有收到照片" in response.json()["detail"]


def test_closet_list_patch_and_delete(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    patched = client.patch(
        f"/closet/items/{created['item_id']}",
        json={"category": "dress", "style_tags": ["通勤"], "note": "显白", "favorite": True},
    )
    assert patched.status_code == 200
    assert patched.json()["category"] == "dress"
    assert patched.json()["favorite"] is True

    listed = client.get("/closet/items?category=dress")
    assert listed.json()["total"] == 1

    deleted = client.delete(f"/closet/items/{created['item_id']}")
    assert deleted.status_code == 200
    assert client.get("/closet/items").json()["total"] == 0


def test_closet_preferences_persist_current_model(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    updated = client.patch("/closet/preferences", json={"current_model_id": "male_slim_1", "current_stylist_session_id": "session_123"})

    assert updated.status_code == 200
    assert updated.json()["current_model_id"] == "male_slim_1"
    assert updated.json()["current_stylist_session_id"] == "session_123"
    preferences = client.get("/closet/preferences").json()
    assert preferences["current_model_id"] == "male_slim_1"
    assert preferences["current_stylist_session_id"] == "session_123"


def test_webpage_image_url_extraction() -> None:
    html = """
    <html>
      <head>
        <meta property="og:image" content="/cover.jpg" />
        <meta name="twitter:image" content="https://img.example.com/tw.jpg" />
      </head>
      <body><img data-src="//img.example.com/detail.webp"></body>
    </html>
    """

    urls = closet._extract_webpage_image_urls(html, "https://shop.example.com/item/1")

    assert "https://shop.example.com/cover.jpg" in urls
    assert "https://img.example.com/tw.jpg" in urls
    assert "https://img.example.com/detail.webp" in urls


def test_closet_top_item_can_enter_tryon(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on",
        data={"closet_item_id": created["item_id"]},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["input"]["garment_image_id"]
    assert data["status"] in {"failed", "pending", "generated", "review", "needs_retake"}
    if data["status"] == "failed":
        assert data["decision"]["user_message"]


def test_outfit_crud_uses_existing_closet_items(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "通勤套装"}).json()

    assert outfit["title"] == "通勤套装"
    assert outfit["items"][0]["item_id"] == created["item_id"]
    assert outfit["cover_path"].startswith("/user-assets/closet/")
    assert outfit["cover_path"].endswith("/flatlay.png")
    assert outfit["layout_snapshot_path"] == outfit["cover_path"]
    assert outfit["layout_version"] == closet.OUTFIT_LAYOUT_VERSION
    assert outfit["layout_slots"][0]["item_id"] == created["item_id"]
    assert client.get("/closet/outfits").json()["total"] == 1

    patched = client.patch(f"/closet/outfits/{outfit['outfit_id']}", json={"title": "周一通勤", "scene_tags": ["上班"], "favorite": True, "favorite_count": 99})
    assert patched.status_code == 200
    assert patched.json()["title"] == "周一通勤"
    assert patched.json()["favorite"] is True
    assert patched.json()["favorite_count"] == 99

    deleted = client.delete(f"/closet/outfits/{outfit['outfit_id']}")
    assert deleted.status_code == 200
    assert client.get("/closet/outfits").json()["total"] == 0


def test_outfit_from_invalid_item_is_rejected(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post("/closet/outfits", json={"item_ids": ["missing"]})

    assert response.status_code == 404
    assert "没有找到这件衣物" in response.json()["detail"]


def test_outfit_layout_keeps_only_one_pair_of_shoes(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    first = _create_closet_item(client, "shoe-one.png", "shoes", (20, 20, 20))
    second = _create_closet_item(client, "shoe-two.png", "shoes", (80, 80, 80))

    outfit = client.post("/closet/outfits", json={"item_ids": [first["item_id"], second["item_id"]], "title": "鞋子去重"}).json()

    shoe_slots = [slot for slot in outfit["layout_slots"] if slot["slot"] == "shoes"]
    assert len(shoe_slots) == 1
    assert shoe_slots[0]["item_id"] == first["item_id"]
    assert outfit["overflow_items"][0]["item_id"] == second["item_id"]
    assert "一套搭配里先保留一件鞋子" in outfit["warnings"][0]


def test_outfit_layout_keeps_only_one_lower_body_item(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    pants = _create_closet_item(client, "pants.png", "bottom", (80, 120, 220))
    skirt = _create_closet_item(client, "skirt.png", "skirt", (20, 40, 80))

    outfit = client.post("/closet/outfits", json={"item_ids": [pants["item_id"], skirt["item_id"]], "title": "下装去重"}).json()

    slots = [slot["slot"] for slot in outfit["layout_slots"]]
    assert slots.count("bottom") == 1
    assert "skirt" not in slots
    assert outfit["overflow_items"][0]["item_id"] == skirt["item_id"]
    assert "裤子和裙子先保留一个" in outfit["warnings"][0]


def test_outfit_layout_dress_conflicts_with_separate_main_items(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    dress = _create_closet_item(client, "dress.png", "dress", (230, 220, 200))
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (80, 120, 220))

    outfit = client.post("/closet/outfits", json={"item_ids": [dress["item_id"], top["item_id"], bottom["item_id"]], "title": "连衣装主搭"}).json()

    slots = [slot["slot"] for slot in outfit["layout_slots"]]
    assert slots == ["dress"]
    assert [item["item_id"] for item in outfit["overflow_items"]] == [top["item_id"], bottom["item_id"]]
    assert len(outfit["warnings"]) == 2


def test_outfit_list_dedupes_highly_similar_main_axis(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    pants = _create_closet_item(client, "pants.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))

    with_shoes = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], pants["item_id"], shoes["item_id"]], "title": "完整套装"},
    ).json()
    without_shoes = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], pants["item_id"]], "title": "重复主轴"},
    ).json()

    listed = client.get("/closet/outfits").json()

    assert listed["total"] == 1
    assert listed["outfits"][0]["outfit_id"] == with_shoes["outfit_id"]
    assert shoes["item_id"] in listed["outfits"][0]["item_ids"]
    assert listed["outfits"][0]["outfit_id"] != without_shoes["outfit_id"]


def test_tryon_from_outfit_uses_outfit_plan_pipeline(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post("/closet/outfits", json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "试穿套装"}).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"], "photo_mode": "mirror_selfie"},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "from_outfit_plan"
    assert data["source_mode"] == "from_outfit"
    assert data["photo_mode"] == "mirror_selfie"
    assert data["outfit"]["outfit_id"] == outfit["outfit_id"]
    assert data["reference_board_path"].startswith("/user-assets/tryon/")
    assert data["missing_slots"] == []


def test_tryon_from_outfit_without_top_returns_reference_message(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    client.patch(f"/closet/items/{created['item_id']}", json={"category": "shoes"})
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "鞋子参考"}).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["mode"] == "from_outfit_plan"
    assert "上装" in data["missing_slots"]
    assert "下装/裙装" in data["missing_slots"]
    assert data["pipeline"]["outfit_plan"]["status"] == "warn"


def test_tryon_from_outfit_plan_upload_endpoint(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()
    top = _png_bytes(_synthetic_top_image_with_color((220, 60, 105)))
    bottom = _png_bytes(_synthetic_top_image_with_color((40, 60, 90)))
    shoes = _png_bytes(_synthetic_top_image_with_color((20, 20, 20)))
    plan = {
        "title": "直接上传整套",
        "items": [
            {"slot": "top", "category": "top"},
            {"slot": "bottom", "category": "bottom"},
            {"slot": "shoes", "category": "shoes"},
        ],
    }

    response = client.post(
        "/try-on/from-outfit-plan",
        data={"outfit_plan": __import__("json").dumps(plan), "photo_mode": "scene_photo", "scene_label": "咖啡店"},
        files=[
            ("person_image", ("person.png", person, "image/png")),
            ("style_reference_image", ("style.png", top, "image/png")),
            ("item_images", ("top.png", top, "image/png")),
            ("item_images", ("bottom.png", bottom, "image/png")),
            ("item_images", ("shoes.png", shoes, "image/png")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["mode"] == "from_outfit_plan"
    assert data["photo_mode"] == "scene_photo"
    assert data["missing_slots"] == []
    assert data["reference_board_path"].startswith("/user-assets/tryon/")


def test_asis_tryon_from_outfit_uses_real_outfit_plan_and_records(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "ASIS 试穿"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/asis/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"], "photo_mode": "standard"},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["asis_mode"] == "product_tryon"
    assert data["mode"] == "from_outfit_plan"
    assert data["record"]["mode"] == "asis_from_outfit_plan"
    assert data["record"]["image_path"] == data["result"]["image_path"]
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["outfit_id"] == outfit["outfit_id"]


def test_asis_tryon_allows_soft_preset_female_model(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "柔焦预设模特"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "female_medium_1.png").read_bytes()

    response = client.post(
        "/asis/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("female_medium_1.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["pipeline"]["input_quality"]["status"] == "warn"
    assert not data["decision"]["blocking_errors"]


def test_asis_tryon_review_result_is_saved_to_records(monkeypatch, tmp_path: Path) -> None:
    class BackgroundChangedProvider(tryon.TryOnProvider):
        mode = "background_changed_test"

        def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict:
            person = Image.open(person_image).convert("RGB")
            output_path = output_dir / "result_background_changed.png"
            Image.new("RGB", person.size, "#050505").save(output_path, "PNG")
            return {
                "stage": tryon._stage("pass", 0.5, {"provider": self.mode, "result_path": str(output_path)}, []),
                "image_path": output_path,
            }

    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: BackgroundChangedProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "需复核试穿"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "female_medium_1.png").read_bytes()

    response = client.post(
        "/asis/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("female_medium_1.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "review"
    assert data["record"]["status"] == "review"
    assert data["record"]["image_path"] == data["result"]["image_path"]
    assert data["record"]["quality_review"]["status"] == "fail"
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["record_id"] == data["record"]["record_id"]


def test_mock_tryon_from_outfit_creates_local_record(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "模拟试穿"}).json()

    response = client.post("/try-on/mock-from-outfit", data={"outfit_id": outfit["outfit_id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["record"]["image_path"].startswith("/user-assets/closet/")
    assert (tmp_path / "tryon_records_manifest.json").exists()
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["outfit_id"] == outfit["outfit_id"]


def test_delete_tryon_record_hides_it_from_records(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "删除试穿记录"}).json()
    generated = client.post("/try-on/mock-from-outfit", data={"outfit_id": outfit["outfit_id"]}).json()

    deleted = client.delete(f"/closet/tryon-records/{generated['record']['record_id']}")

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 0


def test_asis_demo_page_is_available(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/asis/demo")

    assert response.status_code == 200
    assert "asis" in response.text
    assert "灵感" in response.text
    assert 'window.location.href = "/demo?source=asis"' in response.text
    assert 'id="modelCell"' in response.text
    assert 'id="modelSheet"' in response.text
    assert "预设模特" in response.text
    assert "我的照片" in response.text
    assert "female_medium_1" in response.text
    assert 'id="aiPromptInput"' in response.text
    assert 'data-profile-view="works"' in response.text
    assert 'data-work-view="outfits"' in response.text
    assert 'data-work-view="items"' in response.text
    assert "我的作品" in response.text
    assert "isUserCreatedItem" in response.text
    assert "isUserCreatedOutfit" in response.text
    assert "deleteSelectedWorks" in response.text
    assert 'placeholder="向灵感发送消息"' in response.text
    assert "xiaohongshu_preferred: useXHSSkill" in response.text
    assert "面试" in response.text
    assert "怎么穿" in response.text
    assert "requested_skills" in response.text
    assert 'session_id: state.currentSessionId || "asis-inspiration"' in response.text
    assert 'stylistSessionStoreKey = "asis_demo_current_stylist_session"' in response.text
    assert "writeStore(stylistSessionStoreKey, session.session_id)" in response.text
    assert "current_stylist_session_id" in response.text
    assert 'id="sessionPickerBtn"' in response.text
    assert 'id="sessionSheetNew"' in response.text
    assert 'class="session-sidebar"' in response.text
    assert 'id="sessionBackdrop"' in response.text
    assert 'id="sessionActionPopover"' in response.text
    assert 'id="sessionConfirmDeleteBtn"' in response.text
    assert 'id="newSessionBtn"' not in response.text
    assert 'id="aiPromptText"' not in response.text
    assert "找小红书参考" in response.text
    assert "xhs-note-card" in response.text
    assert "ai-toolchain" in response.text
    assert "ai-tool-history" in response.text
    assert "data-ai-toggle-tools" in response.text
    assert "function renderAssistantMarkdown" in response.text
    assert "ai-md-list" in response.text
    assert "function normalizeAIInputText" in response.text
    assert "insertNormalizedPromptText" in response.text
    assert "is-generating" in response.text
    assert '.replace(/\\r\\n?/g, "\\n")' in response.text


def test_wearwow_demo_route_keeps_asis_compatibility(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/wearwow/demo")

    assert response.status_code == 200
    assert "AS IS" in response.text
    assert "灵感" in response.text
    assert "AI穿搭师" not in response.text

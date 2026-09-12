import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app import image_delivery as delivery, material_assets


@pytest.fixture
def images(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, "CACHE", tmp_path / "cache")
    source = tmp_path / "static"
    source.mkdir()
    photo = source / "photo.png"
    image = Image.new("RGBA", (1800, 2400), (25, 90, 150, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(photo)
    app = FastAPI()
    app.mount("/static", delivery.ImageStaticFiles(directory=source))

    @app.get("/private/photo")
    def private(request: Request, download: bool = False):
        if request.headers.get("authorization") != "Bearer owner":
            raise HTTPException(401)
        return delivery.ImageFileResponse(photo, headers={"Cache-Control": "private, max-age=300"},
                                          filename="original.png" if download else None)

    return TestClient(app), photo, app


def test_webp_is_proportional_has_alpha_and_keeps_original(images):
    client, source, _ = images
    original = source.read_bytes()
    response = client.get("/static/photo.png", headers={"Accept": "image/webp,image/*"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["vary"] == "Accept"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.format == "WEBP" and image.size == (1200, 1600)
        assert image.mode == "RGBA" and image.getpixel((0, 0))[3] < 255
        assert not image.getexif()
    assert client.get("/static/photo.png").content == original
    assert client.get("/static/photo.png?format=original", headers={"Accept": "image/webp"}).content == original
    assert client.get("/static/photo.png", headers={"Accept": "image/webp;q=0,image/png"}).content == original
    assert client.get("/static/photo.png?format=webp").content == response.content
    assert source.read_bytes() == original


def test_cache_etag_head_and_concurrent_first_requests(images):
    client, source, _ = images
    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(lambda _: delivery.preview_path(source), range(4)))
    assert len(set(files)) == 1
    cached = files[0]
    stamp = cached.stat().st_mtime_ns
    response = client.get("/static/photo.png?format=webp")
    assert client.head("/static/photo.png?format=webp").headers["content-length"] == str(len(response.content))
    unchanged = client.get("/static/photo.png?format=webp", headers={"If-None-Match": response.headers["etag"]})
    assert unchanged.status_code == 304 and unchanged.headers["vary"] == "Accept"
    original_etag = client.get("/static/photo.png").headers["etag"]
    assert client.get("/static/photo.png?format=webp", headers={"If-None-Match": original_etag}).status_code == 200
    assert cached.stat().st_mtime_ns == stamp
    Image.new("RGB", (60, 80), "red").save(source)
    changed = client.get("/static/photo.png?format=webp", headers={"If-None-Match": response.headers["etag"]})
    assert changed.status_code == 200 and changed.content != response.content


def test_cached_private_preview_still_requires_owner_and_download_is_original(images):
    client, source, _ = images
    auth = {"Authorization": "Bearer owner", "Accept": "image/webp"}
    preview = client.get("/private/photo", headers=auth)
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/webp"
    assert preview.headers["cache-control"].startswith("private")
    assert client.get("/private/photo?format=webp").status_code == 401
    assert client.get("/private/photo?download=true", headers=auth).content == source.read_bytes()
    assert client.get("/static/../photo.png?format=webp").status_code == 404


def test_registered_public_and_private_materials_use_same_origin_webp(images, tmp_path, monkeypatch):
    client, photo, app = images
    registry = material_assets.MaterialRegistry(tmp_path / "registry.json")
    aid = registry.register(photo.read_bytes(), "https://cdn.example.test/photo.png", "image/png")
    monkeypatch.setattr(material_assets, "MaterialRegistry", lambda: registry)
    calls = []
    monkeypatch.setattr(material_assets, "material_image_path", lambda asset_id: calls.append(asset_id) or photo)
    app.include_router(material_assets.router)
    url = material_assets.asset_content_url(aid)
    assert client.get(url, follow_redirects=False).headers["location"].startswith("https://cdn.example.test/")
    response = client.get(url + "?format=webp")
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert calls == [aid]
    data = json.loads(registry.path.read_text())
    data["assets"][aid]["storage"] = {"private": True}
    material_assets.write_json_atomic(registry.path, data)
    assert client.get(url, headers={"Accept": "image/webp"}).content == response.content
    assert client.get(url + "?format=original").content == photo.read_bytes()
    registry.path.write_text('{"schemaVersion":"1.0","assets":{}}')
    assert client.get(url + "?format=webp").status_code == 404


def test_exif_rotation_small_files_and_non_images(images):
    client, photo, _ = images
    jpeg = photo.with_suffix(".jpg")
    image = Image.new("RGB", (20, 30), "orange")
    exif = Image.Exif(); exif[274] = 6
    image.save(jpeg, exif=exif)
    result = client.get("/static/photo.jpg?format=webp")
    with Image.open(io.BytesIO(result.content)) as preview:
        assert preview.size == (30, 20)
    (photo.parent / "test.html").write_text("<html>OK</html>")
    assert client.get("/static/test.html?format=webp").text == "<html>OK</html>"

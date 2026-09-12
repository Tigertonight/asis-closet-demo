"""Display copies are small, cached and isolated from try-on originals."""
import hashlib
import io
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app import material_assets, model_assets, selfit_studio, tryon


@pytest.fixture
def models(monkeypatch, tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    original = root / "male.png"
    Image.new("RGB", (1792, 2400), "#dcbdab").save(original)
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"items": [
        {"id": "male", "file": "male.png", "gender": "male", "active": True},
        {"id": "hidden", "file": "male.png", "active": False},
        {"id": "outside", "file": "../outside.png"},
    ]}))
    Image.new("RGB", (4, 6)).save(tmp_path / "outside.png")
    monkeypatch.setattr(tryon, "TRYON_MODEL_FIXTURE_DIR", root)
    monkeypatch.setattr(model_assets, "MODEL_PREVIEW_CACHE", tmp_path / "previews")
    app = FastAPI()
    app.include_router(selfit_studio.router)
    return TestClient(app), root, original, manifest


def test_preview_is_small_proportional_cached_and_preserves_original(models):
    client, root, original, _ = models
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    model = client.get("/selfit/try-on/models").json()["items"][0]
    assert model["image_url"].startswith("/tryon-models/male.png")
    response = client.get(model["preview_url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "max-age=" in response.headers["cache-control"]
    with Image.open(io.BytesIO(response.content)) as photo:
        assert photo.size == (956, 1280)
        assert abs(photo.width / photo.height - 1792 / 2400) < .001
    assert len(response.content) < len(original.read_bytes())
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    cached = model_assets.model_preview_path(root, "male")
    stamp = cached.stat().st_mtime_ns
    assert client.get(model["preview_url"]).content == response.content
    assert cached.stat().st_mtime_ns == stamp
    # New source bytes invalidate both the URL and the generated cache.
    Image.new("RGB", (900, 1200), "#336699").save(original)
    updated = client.get("/selfit/try-on/models").json()["items"][0]
    assert updated["preview_url"] != model["preview_url"]
    assert client.get(updated["preview_url"]).content != response.content


@pytest.mark.parametrize("mid", ["hidden", "outside", "missing"])
def test_preview_rejects_unavailable_or_unsafe_models(models, mid):
    client, *_ = models
    assert client.get(f"/selfit/try-on/models/{mid}/preview").status_code == 404


def test_material_model_preview_reuses_verified_original_and_warm_cache(models, monkeypatch, tmp_path):
    client, root, original, manifest = models
    registry = material_assets.MaterialRegistry(tmp_path / "assets.json")
    asset_id = registry.register(original.read_bytes(), "/static/male.png", "image/png")
    monkeypatch.setattr(material_assets, "MaterialRegistry", lambda: registry)
    monkeypatch.setattr(model_assets, "MaterialRegistry", lambda: registry)
    calls = []
    def resolve(aid):
        calls.append(aid)
        return original
    monkeypatch.setattr(material_assets, "material_image_path", resolve)
    manifest.write_text(json.dumps({"items": [{"id": "male", "file": "absent.png", "image_asset_id": asset_id}]}))
    model = client.get("/selfit/try-on/models").json()["items"][0]
    assert model["image_url"] == material_assets.asset_content_url(asset_id)
    assert client.get(model["preview_url"]).status_code == 200
    assert client.get(model["preview_url"]).status_code == 200
    assert calls == [asset_id], "warm preview must not redownload/read the full original"
    registry.path.write_text('{"schemaVersion":"1.0","assets":{}}')
    assert client.get(model["preview_url"]).status_code == 404

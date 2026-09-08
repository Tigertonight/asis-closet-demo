import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.material_assets import (
    MaterialRegistry, asset_content_url, asset_id_for_bytes, resolve_asset_url,
    resolve_image_references, router,
)
from scripts.register_material_assets import browser_catalog_script, register_catalog_images
from scripts.upload_content_pool import upload_directory


def test_id_survives_cdn_move_and_registry_reloads(tmp_path):
    registry = MaterialRegistry(tmp_path / "materials.json")
    asset_id = registry.register(b"picture", "/static/one.png", "image/png")
    reader = MaterialRegistry(registry.path)
    assert resolve_asset_url(asset_id, reader) == "/static/one.png"
    assert registry.register(b"picture", "https://cdn.example.com/one.png", "image/png") == asset_id
    assert resolve_asset_url(asset_id, reader) == "https://cdn.example.com/one.png"
    assert registry.register(b"new-picture", "/static/one.png?v=2", "image/png") != asset_id
    registry.register(b"picture", "/static/one.png", "image/png", replace_url=False)
    assert resolve_asset_url(asset_id, reader).startswith("https://cdn.example.com/")


def test_parallel_registration_does_not_lose_records(tmp_path):
    path = tmp_path / "materials.json"
    def register(index):
        return MaterialRegistry(path).register(str(index).encode(), f"/static/{index}.png", "image/png")
    with ThreadPoolExecutor(max_workers=8) as workers:
        ids = list(workers.map(register, range(24)))
    assert set(json.loads(path.read_text())["assets"]) == set(ids)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "//evil.test/a", "/outputs/private.jpg",
                                      "/static/../.env", "/static/%2e%2e/.env", "https://user:secret@example.com/a"])
def test_rejects_non_public_material_paths(tmp_path, url):
    with pytest.raises(ValueError):
        MaterialRegistry(tmp_path / "materials.json").register(b"x", url, "image/png")


def test_corrupt_registry_is_not_overwritten(tmp_path):
    path = tmp_path / "materials.json"
    path.write_text("broken JSON")
    with pytest.raises(ValueError):
        MaterialRegistry(path).register(b"x", "/static/a.png", "image/png")
    assert path.read_text() == "broken JSON"


def test_resolver_uses_ids_keeps_legacy_urls_and_does_not_mutate(tmp_path):
    registry = MaterialRegistry(tmp_path / "materials.json")
    asset_id = registry.register(b"picture", "/static/a.png", "image/png")
    payload = {"image": {"assetId": asset_id}, "avatars": {"imageAssetId": asset_id},
               "old": {"src": "/static/old.png"}}
    runtime = resolve_image_references(payload, registry)
    assert "src" not in payload["image"]
    assert runtime["image"]["src"] == asset_content_url(asset_id)
    assert runtime["avatars"]["imageUrl"] == asset_content_url(asset_id)
    assert runtime["old"]["src"] == "/static/old.png"
    assert resolve_image_references(payload, registry, indirect=False)["image"]["src"] == "/static/a.png"
    with pytest.raises(KeyError):
        resolve_image_references({"assetId": asset_id_for_bytes(b"absent")}, registry)


class FakeS3:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def put_object(self, **kwargs):
        if len(self.calls) == self.fail_at:
            raise RuntimeError("Upload failed")
        self.calls.append(kwargs)


@pytest.mark.parametrize("workers", [1, 4])
def test_upload_same_name_different_folders_deduplicates_by_bytes(tmp_path, workers):
    source = tmp_path / "images"
    for folder, content in (("a", b"one"), ("b", b"two"), ("c", b"one")):
        (source / folder).mkdir(parents=True)
        (source / folder / "photo.png").write_bytes(content)
    registry = MaterialRegistry(tmp_path / "materials.json")
    client = FakeS3()
    result = upload_directory(source, client=client, bucket="public", public_base="https://cdn.example.com", registry=registry, workers=workers)
    assert len(client.calls) == 2
    assert len({call["Key"] for call in client.calls}) == 2
    refs = result["files"]
    assert refs["a/photo.png"] == refs["c/photo.png"] != refs["b/photo.png"]
    assert set(refs["a/photo.png"]) == {"assetId"}
    for entry in refs.values():
        assert resolve_asset_url(entry["assetId"], registry).startswith("https://cdn.example.com/report/v1/asset_")
    migrated = upload_directory(source, client=FakeS3(), bucket="new", public_base="https://new.example.com", registry=registry)
    assert migrated == result
    assert resolve_asset_url(refs["a/photo.png"]["assetId"], registry).startswith("https://new.example.com/")


def test_partial_upload_only_registers_successes(tmp_path):
    source = tmp_path / "images"
    source.mkdir()
    (source / "a.png").write_bytes(b"one")
    (source / "b.png").write_bytes(b"two")
    registry = MaterialRegistry(tmp_path / "materials.json")
    old_id = registry.register(b"two", "https://old.example.com/b.png", "image/png")
    with pytest.raises(RuntimeError, match="Upload failed"):
        upload_directory(source, client=FakeS3(fail_at=1), bucket="public", public_base="https://cdn.example.com", registry=registry)
    assert set(json.loads((source / "manifest.json").read_text())["files"]) == {"a.png"}
    assert resolve_asset_url(old_id, registry) == "https://old.example.com/b.png"


def test_upload_can_resume_without_writing_into_source_or_resending_successes(tmp_path):
    source = tmp_path / "delivery"
    source.mkdir()
    (source / "a.png").write_bytes(b"one")
    registry = MaterialRegistry(tmp_path / "registry.json")
    manifest = tmp_path / "result.json"
    result = upload_directory(source, client=FakeS3(), bucket="public", public_base="https://cdn.example.com",
                              registry=registry, manifest_path=manifest)
    assert not (source / "manifest.json").exists()
    resumed = upload_directory(source, client=FakeS3(fail_at=0), bucket="public", public_base="https://cdn.example.com",
                               registry=registry, manifest_path=manifest)
    assert result == resumed


def test_catalog_migration_is_idempotent_and_does_not_replace_cdn(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "a.png").write_bytes(b"picture")
    registry = MaterialRegistry(tmp_path / "materials.json")
    asset_id = registry.register(b"picture", "https://cdn.example.com/a.png", "image/png")
    catalog = {"image": {"src": "../../static/a.png", "alt": "A"}, "sourceUrl": "https://example.com/note"}
    result = register_catalog_images(catalog, registry, static_root=static)
    assert result == {"image": {"assetId": asset_id, "alt": "A"}, "sourceUrl": catalog["sourceUrl"]}
    assert register_catalog_images(result, registry, static_root=static) == result
    assert resolve_asset_url(asset_id, registry) == "https://cdn.example.com/a.png"
    assert "https://cdn.example.com" not in browser_catalog_script(result, registry)


def test_public_lookup_redirect_and_missing_id(tmp_path, monkeypatch):
    registry = MaterialRegistry(tmp_path / "materials.json")
    monkeypatch.setenv("SELFIT_MATERIAL_REGISTRY_PATH", str(registry.path))
    static = tmp_path / "static"
    static.mkdir()
    (static / "a.png").write_bytes(b"picture")
    asset_id = registry.register(b"picture", "/static/a.png", "image/png")
    app = FastAPI()
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=static))
    client = TestClient(app)
    metadata = client.get(f"/api/v1/material-assets/{asset_id}")
    assert metadata.json()["url"] == "/static/a.png"
    assert metadata.json()["assetId"] == asset_id
    url = asset_content_url(asset_id)
    assert client.get(url).content == b"picture"
    registry.register(b"picture", "https://cdn.example.com/new.png", "image/png")
    redirect = client.get(url, follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://cdn.example.com/new.png"
    assert redirect.headers["cache-control"] == "no-store"
    for missing in ("unknown", asset_id_for_bytes(b"missing")):
        assert client.get(f"/api/v1/material-assets/{missing}").status_code == 404
        assert client.get(f"/api/v1/material-assets/{missing}/content").status_code == 404


def test_all_report_templates_use_registered_assets_and_generated_js_matches():
    from app.selfit_report import PERSONALITY_TEMPLATE_PATH, default_personality_report
    registry = MaterialRegistry()
    catalog = json.loads(PERSONALITY_TEMPLATE_PATH.read_text())
    resolved = resolve_image_references(catalog, registry)
    root = Path(__file__).resolve().parents[1]
    script = (root / "app/static/selfit/personality-report-templates.js").read_text()
    assert script == browser_catalog_script(catalog, registry)
    # Check actual source bytes too: an existing JSON entry alone is insufficient.
    records = json.loads(registry.path.read_text())["assets"]
    assert records
    for record in records.values():
        if not record["url"].startswith("/static/"):
            continue
        path = root / "app" / record["url"].split("?", 1)[0].lstrip("/")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    for code, template in catalog["types"].items():
        assert "src" not in template["hero"]["image"]
        report = default_personality_report(code)
        assert report["heroImage"] == resolved["types"][code]["hero"]["image"]
        for section in ("makeup", "hair", "outfits"):
            for card in report[section]:
                assert card["assetId"]
                assert card["imageUrl"] == asset_content_url(card["assetId"])


def test_shared_report_keeps_material_images_but_excludes_private_routes():
    from app.selfit_report import default_personality_report
    from app.selfit_share import sanitize_public_report
    report = default_personality_report("mute")
    public = sanitize_public_report(report)
    assert public["heroImage"]["src"] == report["heroImage"]["src"]
    assert public["source"]["avatars"]["imageUrl"] == report["source"]["avatars"]["imageUrl"]
    assert public["makeup"][0]["imageUrl"] == report["makeup"][0]["imageUrl"]
    report["heroImage"]["src"] = "/api/v1/selfit/sessions/private/photos/face/preview"
    assert "src" not in sanitize_public_report(report)["heroImage"]

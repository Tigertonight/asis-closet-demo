"""Keep legacy model URLs working when the master image lives in object storage."""
import json
import hashlib
from pathlib import Path

from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from app.material_assets import MaterialRegistry, asset_content_url


def load_model_manifest(directory):
    """Apply optional local model metadata only to the exact local photo bytes.

    Unpublished originals and manifest.local.json stay on the operator's machine.
    Other checkouts retain the shared Git models and reject unrelated presets.
    """
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    local = root / "manifest.local.json"
    if not local.is_file():
        return manifest
    overrides = json.loads(local.read_text()).get("models", {})
    for index, row in enumerate(manifest["items"]):
        mid = row.get("id") or Path(row.get("file", "")).stem
        override = overrides.get(mid, {})
        metadata = override.get("metadata", {})
        source = (root / row.get("file", "")).resolve()
        if (metadata.get("file") == row.get("file") and metadata.get("gender") == row.get("gender")
                and (metadata.get("id") or Path(metadata.get("file", "")).stem) == mid
                and source.parent == root and source.is_file()
                and hashlib.sha256(source.read_bytes()).hexdigest() == override.get("sha256")):
            manifest["items"][index] = metadata
    return manifest


class ModelStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        manifest = Path(self.directory) / "manifest.json"
        if manifest.is_file():
            rows = load_model_manifest(self.directory)["items"]
            matches = [row for row in rows if row.get("file") == path and row.get("image_asset_id")]
            if len(matches) == 1:
                asset_id = matches[0]["image_asset_id"]
                MaterialRegistry().get(asset_id)
                return RedirectResponse(asset_content_url(asset_id), headers={"Cache-Control": "no-cache"})
        return await super().get_response(path, scope)

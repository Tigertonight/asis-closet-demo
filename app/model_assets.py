"""Keep legacy model URLs working when the master image lives in object storage."""
import json
import hashlib
import tempfile
from pathlib import Path
from threading import RLock
from urllib.parse import quote

from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from app.material_assets import MaterialRegistry, asset_content_url

MODEL_PREVIEW_CACHE = Path(__file__).resolve().parents[1] / "outputs/model-previews"
MODEL_PREVIEW_VERSION = "webp-960x1280-q84-v1"
_preview_lock = RLock()


def model_preview_url(model_id: str, image_url: str) -> str:
    version = hashlib.sha256(f"{MODEL_PREVIEW_VERSION}:{image_url}".encode()).hexdigest()[:16]
    return f"/selfit/try-on/models/{quote(model_id, safe='')}/preview?v={version}"


def model_preview_path(directory: Path, model_id: str) -> Path:
    """Cache a display-sized copy; generation keeps the original model bytes."""
    from PIL import Image, ImageOps
    from app.material_assets import material_image_path

    root = Path(directory).resolve()
    row = next((row for row in load_model_manifest(root)["items"]
                if row.get("active") is not False
                and (row.get("id") or Path(row.get("file", "")).stem) == model_id), None)
    if row is None:
        raise KeyError(model_id)
    asset_id = row.get("image_asset_id")
    if asset_id:
        # Check the current registry even on a cache hit; removed models stay removed.
        record = MaterialRegistry().get(asset_id)
        identity = record["sha256"]
        source = None
    else:
        source = (root / row.get("file", "")).resolve()
        if source.parent != root or not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise KeyError(model_id)
        stat = source.stat()
        identity = f"{source}:{stat.st_mtime_ns}:{stat.st_size}"
    key = hashlib.sha256(f"{MODEL_PREVIEW_VERSION}:{identity}".encode()).hexdigest()
    target = MODEL_PREVIEW_CACHE / f"{key}.webp"
    with _preview_lock:
        if target.is_file():
            return target
        source = source or material_image_path(asset_id)
        with Image.open(source) as original:
            preview = ImageOps.exif_transpose(original).convert("RGB")
            preview.thumbnail((960, 1280), Image.Resampling.LANCZOS)
            MODEL_PREVIEW_CACHE.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=MODEL_PREVIEW_CACHE, suffix=".webp", delete=False) as tmp:
                temporary = Path(tmp.name)
            try:
                preview.save(temporary, format="WEBP", quality=84, method=4)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    return target


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

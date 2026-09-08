"""Public material IDs and their current URLs; never register private user photos here.

Business JSON stores assetId (image.src) or imageAssetId (imageUrl). IDs are the
SHA-256 of the bytes, so re-uploading or moving a CDN does not change references.
"""

from __future__ import annotations

import copy
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "app/data/material-assets.v1.json"
ID_PATTERN = re.compile(r"asset_[0-9a-f]{64}")
IMAGE_ID_FIELDS = {"assetId": "src", "imageAssetId": "imageUrl"}


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url)
    if not url or any(ord(char) < 33 for char in url) or "\\" in url:
        raise ValueError("Material URL must be a public HTTP(S) URL or /static/ path")
    if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
        return url
    if not parsed.scheme and not parsed.netloc and parsed.path.startswith("/static/"):
        if ".." not in unquote(parsed.path).split("/"):
            return url
    raise ValueError("Material URL must be a public HTTP(S) URL or /static/ path")


def asset_id_for_bytes(data: bytes) -> str:
    return "asset_" + hashlib.sha256(data).hexdigest()


def asset_content_url(asset_id: str) -> str:
    if not ID_PATTERN.fullmatch(asset_id):
        raise ValueError("Invalid material asset ID")
    return f"/api/v1/material-assets/{asset_id}/content"


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": "1.0", "assets": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0" or not isinstance(payload.get("assets"), dict):
        raise ValueError(f"Invalid material registry: {path}")
    for asset_id, record in payload["assets"].items():
        if not ID_PATTERN.fullmatch(asset_id) or not isinstance(record, dict) or record.get("sha256") != asset_id[6:]:
            raise ValueError(f"Invalid material record: {asset_id}")
        validate_public_url(record.get("url", ""))
    return payload


@lru_cache(maxsize=8)
def _cached_registry(path: str, stamp: tuple[int, int, int]) -> dict[str, Any]:
    return _read_registry(Path(path))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".material-", delete=False) as output:
            temporary = output.name
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class MaterialRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or os.getenv("SELFIT_MATERIAL_REGISTRY_PATH") or DEFAULT_REGISTRY_PATH).resolve()

    def get(self, asset_id: str) -> dict[str, Any]:
        if not ID_PATTERN.fullmatch(asset_id):
            raise KeyError(asset_id)
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            raise KeyError(asset_id) from None
        payload = _cached_registry(str(self.path), (stat.st_mtime_ns, stat.st_size, stat.st_ino))
        return copy.deepcopy(payload["assets"][asset_id])

    def register(self, data: bytes, url: str, content_type: str, *, replace_url: bool = True,
                 storage: dict[str, Any] | None = None) -> str:
        """Call after a successful upload. Lock + atomic replace prevent lost updates.

        Local catalog imports use replace_url=False to retain an existing CDN URL.
        """
        validate_public_url(url)
        asset_id = asset_id_for_bytes(data)
        record = {"url": url, "sha256": asset_id[6:], "contentType": content_type, "bytes": len(data)}
        if storage is not None:
            if (storage.get("provider") != "qiniu" or not storage.get("bucket") or not storage.get("key")
                    or not isinstance(storage.get("private"), bool)):
                raise ValueError("Invalid Qiniu storage metadata")
            record["storage"] = copy.deepcopy(storage)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            payload = _read_registry(self.path)
            previous = payload["assets"].get(asset_id)
            if previous and not replace_url:
                return asset_id
            if previous != record:
                payload["assets"][asset_id] = record
                payload["assets"] = dict(sorted(payload["assets"].items()))
                write_json_atomic(self.path, payload)
        return asset_id


def resolve_asset_url(asset_id: str, registry: MaterialRegistry | None = None) -> str:
    return (registry or MaterialRegistry()).get(asset_id)["url"]


def material_download_url(record: dict[str, Any]) -> str:
    """Generate private download authorization at read time; never persist tokens."""
    storage = record.get("storage", {})
    if storage.get("provider") != "qiniu" or not storage.get("private"):
        return record["url"]
    from dotenv import dotenv_values
    values = dotenv_values(Path(os.getenv("QINIU_ENV_FILE") or ROOT / ".env.qiniu"))
    access_key = os.getenv("QINIU_ACCESS_KEY") or values.get("QINIU_ACCESS_KEY")
    secret_key = os.getenv("QINIU_SECRET_KEY") or values.get("QINIU_SECRET_KEY")
    if not access_key or not secret_key:
        raise ValueError("Qiniu download credentials are not configured")
    url = record["url"]
    unsigned = f"{url}{'&' if '?' in url else '?'}e={int(time.time()) + 3600}"
    signature = base64.urlsafe_b64encode(hmac.new(secret_key.encode(), unsigned.encode(), hashlib.sha1).digest()).decode()
    return f"{unsigned}&token={access_key}:{signature}"


def material_image_path(asset_id: str, registry: MaterialRegistry | None = None) -> Path:
    """Resolve verified material bytes, including private objects, to a local cache."""
    import io
    import httpx
    from PIL import Image

    record = (registry or MaterialRegistry()).get(asset_id)
    parsed = urlsplit(record["url"])
    if not parsed.scheme:
        path = (ROOT / "app" / unquote(parsed.path).lstrip("/")).resolve()
        if not path.is_relative_to(ROOT / "app/static") or not path.is_file():
            raise ValueError("Missing local material")
    else:
        cache = ROOT / "outputs/material-cache"
        path = cache / (asset_id + ".image")
        if not path.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            chunks, size = [], 0
            with httpx.stream("GET", material_download_url(record), timeout=30, follow_redirects=False) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 32 * 1024 * 1024:
                        raise ValueError("Material is too large")
                    chunks.append(chunk)
            raw = b"".join(chunks)
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("Material hash mismatch")
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temp:
                temp.write(raw)
                temporary = Path(temp.name)
            temporary.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError("Material hash mismatch")
    return path


def resolve_image_references(value: Any, registry: MaterialRegistry | None = None, *, indirect: bool = True) -> Any:
    """Copy business data and add render URLs, accepting legacy URL-only records.

    Indirect URLs also keep already-saved reports valid when the CDN URL changes.
    Unknown IDs fail explicitly instead of silently rendering an unrelated image.
    """
    registry = registry or MaterialRegistry()
    if isinstance(value, list):
        return [resolve_image_references(item, registry, indirect=indirect) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: resolve_image_references(item, registry, indirect=indirect) for key, item in value.items()}
    for id_field, url_field in IMAGE_ID_FIELDS.items():
        if result.get(id_field):
            asset_id = result[id_field]
            url = resolve_asset_url(asset_id, registry)
            result[url_field] = asset_content_url(asset_id) if indirect else url
    return result


router = APIRouter(prefix="/api/v1/material-assets", tags=["material-assets"])


def _public_record(asset_id: str) -> dict[str, Any]:
    try:
        return MaterialRegistry().get(asset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="素材不存在") from None


@router.get("/{asset_id}")
def material_metadata(asset_id: str):
    from fastapi.responses import JSONResponse

    return JSONResponse({"assetId": asset_id, **_public_record(asset_id)}, headers={"Cache-Control": "no-store"})


@router.get("/{asset_id}/content")
def material_content(asset_id: str):
    record = _public_record(asset_id)
    if record.get("storage", {}).get("private"):
        import httpx
        from fastapi.responses import FileResponse
        try:
            path = material_image_path(asset_id)
        except (OSError, ValueError, httpx.HTTPError):
            raise HTTPException(503, "素材暂时无法读取，请稍后重试。") from None
        # Same-origin delivery supports HTTPS pages even with an HTTP-only origin.
        return FileResponse(path, media_type=record["contentType"], headers={"Cache-Control": "public, max-age=3600"})
    return RedirectResponse(record["url"], status_code=307, headers={"Cache-Control": "no-store"})

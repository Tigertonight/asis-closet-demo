"""Cached WebP display copies; original URLs/bytes remain usable by generators.

Conversion happens after the owning route has authorized and resolved the file.
The cache is not mounted publicly. Never accept a caller-supplied source path/URL.
"""
from __future__ import annotations

import fcntl
import hashlib
import logging
import os
from pathlib import Path
import tempfile
from threading import BoundedSemaphore
from urllib.parse import parse_qs

from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

CACHE = Path(__file__).resolve().parents[1] / "outputs/image-previews"
VERSION = "webp-1600-q84-v1"
BOUNDS = (1600, 1600)
RASTER_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}
logger = logging.getLogger(__name__)
_encoders = BoundedSemaphore(2)


def wants_webp(scope: dict) -> bool:
    if scope.get("path", "").endswith("/download"):
        return False
    query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
    if query.get("format") == ["original"] or query.get("download") in (["1"], ["true"]):
        return False
    if query.get("format") == ["webp"]:
        return True
    for item in Headers(scope=scope).get("accept", "").lower().split(","):
        mime, *params = item.strip().split(";")
        if mime == "image/webp":
            try:
                return all(float(p.strip()[2:]) > 0 for p in params if p.strip().startswith("q="))
            except ValueError:
                return False
    return False


def preview_path(source: Path) -> Path:
    source = source.resolve()
    stat = source.stat()
    identity = f"{VERSION}:{source}:{stat.st_mtime_ns}:{stat.st_size}"
    key = hashlib.sha256(identity.encode()).hexdigest()
    target = CACHE / (key + ".webp")
    if target.is_file():
        return target
    if source.suffix.lower() == ".webp":
        with Image.open(source) as existing:
            if existing.format == "WEBP" and existing.width <= BOUNDS[0] and existing.height <= BOUNDS[1] and not existing.getexif():
                return source
    CACHE.mkdir(parents=True, exist_ok=True)
    # Per-image lock works across workers without blocking unrelated pictures.
    with (CACHE / (key + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_file():
            return target
        with _encoders, Image.open(source) as original:
            if original.width * original.height > 40_000_000:
                raise ValueError("Display image exceeds the conversion pixel limit")
            if original.format == "WEBP" and original.width <= BOUNDS[0] and original.height <= BOUNDS[1] and not original.getexif():
                return source
            image = ImageOps.exif_transpose(original)
            image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
            image.thumbnail(BOUNDS, Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(dir=CACHE, suffix=".webp", delete=False) as output:
                temporary = Path(output.name)
            try:
                image.save(temporary, "WEBP", quality=84, method=4)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
    return target


class ImageFileResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        response = self
        raster = self.media_type and self.media_type.split(";")[0] in RASTER_TYPES
        attachment = self.headers.get("content-disposition", "").startswith("attachment")
        if raster and not attachment:
            vary = [part.strip() for part in self.headers.get("vary", "").split(",") if part.strip()]
            if "accept" not in [part.lower() for part in vary]:
                vary.append("Accept")
            self.headers["Vary"] = ", ".join(vary)
            if wants_webp(scope):
                try:
                    path = await run_in_threadpool(preview_path, Path(self.path))
                    headers = {key: value for key, value in self.headers.items()
                               if key not in {"content-type", "content-length", "etag", "last-modified"}}
                    response = FileResponse(path, media_type="image/webp", headers=headers,
                                            background=self.background, status_code=self.status_code)
                    response.set_stat_headers(path.stat())
                except (OSError, ValueError, Image.DecompressionBombError):
                    # A display derivative must not make a readable original unavailable.
                    logger.warning("Image display conversion failed", exc_info=True)
        # Validate against the selected representation, never the original's ETag.
        if response.stat_result is None and "etag" not in response.headers:
            response.set_stat_headers(await run_in_threadpool(os.stat, response.path))
        if scope.get("method") in {"GET", "HEAD"} and StaticFiles().is_not_modified(response.headers, Headers(scope=scope)):
            headers = {key: value for key, value in response.headers.items()
                       if key in {"cache-control", "etag", "last-modified", "vary"}}
            await Response(status_code=304, headers=headers)(scope, receive, send)
            return
        if response is self:
            await super().__call__(scope, receive, send)
        else:
            await response(scope, receive, send)


class ImageStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200):
        return ImageFileResponse(full_path, stat_result=stat_result, status_code=status_code)

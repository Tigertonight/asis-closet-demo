"""Bundled onboarding photos: original-byte analysis and disposable display caches."""

from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PIL import Image, ImageOps

from app import selfit_photo
from app.storage import ROOT_DIR

SAMPLE_DIR = Path(__file__).parent / "static/selfit/assets/samples"
CACHE_DIR = ROOT_DIR / "outputs/selfit-samples"
CACHE_VERSION = "samples-v1"


@dataclass(frozen=True)
class SamplePhoto:
    id: str
    gender: str
    kind: str
    filename: str

    @property
    def path(self) -> Path:
        return SAMPLE_DIR / self.filename


SAMPLES = {
    s.id: s for s in (
        SamplePhoto("female-face", "female", "face", "female-face-sample.png"),
        SamplePhoto("female-body", "female", "body", "female-body-sample-v2.jpg"),
        SamplePhoto("male-face", "male", "face", "male-face-sample.png"),
        SamplePhoto("male-body", "male", "body", "male-body-sample.png"),
    )
}
_locks = {key: threading.RLock() for key in SAMPLES}


@lru_cache(maxsize=64)
def _file_digest(path: Path, size: int, mtime: int, ctime: int) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_digest(path: Path) -> str:
    stat = path.stat()
    return _file_digest(path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@lru_cache(maxsize=1)
def _runtime_versions() -> list[str]:
    result = []
    for package in ("Pillow", "numpy", "opencv-python", "opencv-python-headless", "mediapipe", "colour-science"):
        try:
            result.append(f"{package}:{version(package)}")
        except PackageNotFoundError:
            result.append(f"{package}:missing")
    return result


def _algorithm_files() -> list[str]:
    from app import attribute_pipeline as ap, cv_pipeline as cv

    # Include code and weight contents as well as the declared version, so even
    # a missed version bump cannot silently reuse obsolete sample measurements.
    paths = [Path(selfit_photo.__file__), Path(ap.__file__), Path(cv.__file__),
             ap.POSE_LANDMARKER_MODEL, ap.SELFIE_SEGMENTER_MODEL,
             cv.FACE_DETECTOR_MODEL, cv.FACE_LANDMARKER_MODEL]
    return [file_digest(p) if p.is_file() else "missing" for p in paths]


# Capture the loaded release at process startup. During git-based deployment the
# old worker can briefly run after files change; it must not cache old in-memory
# detectors under the new release's code/weight fingerprint.
_ALGORITHM_FILES = _algorithm_files()
_OVERLAY_RENDERER = file_digest(Path(__file__).parent / "qa_onboarding.py")


def analysis_fingerprint(sample: SamplePhoto) -> str:
    from app.attribute_pipeline import PHOTO_ALGORITHM_VERSION

    parts = [CACHE_VERSION, PHOTO_ALGORITHM_VERSION, sample.id, file_digest(sample.path),
             *_runtime_versions(), *_ALGORITHM_FILES]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temp.write_bytes(content)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def inspect_sample(sample: SamplePhoto, image: Image.Image) -> tuple[selfit_photo.PhotoInspection, str]:
    fingerprint = analysis_fingerprint(sample)
    # Test/debug inspectors must never read or poison the real algorithm cache.
    if selfit_photo._inspector is not selfit_photo.attribute_inspector:
        return selfit_photo.inspect_photo(image, sample.kind), fingerprint
    path = CACHE_DIR / f"{fingerprint}.json"
    with _locks[sample.id]:
        try:
            data = json.loads(path.read_text())
            result = selfit_photo.PhotoInspection(**data["inspection"])
            if data["fingerprint"] == fingerprint and result.accepted and not result.issues:
                return result, fingerprint
        except (OSError, ValueError, KeyError, TypeError):
            pass
        result = selfit_photo.inspect_photo(image, sample.kind)
        # A temporary missing detector/dependency must not become a cached failure.
        if result.accepted and not result.issues:
            _atomic_write(path, json.dumps({"fingerprint": fingerprint, "inspection": asdict(result)},
                                         ensure_ascii=False).encode())
        return result, fingerprint


def preview_path(sample: SamplePhoto, *, overlay: bool = False) -> Path:
    if overlay:
        key = f"{analysis_fingerprint(sample)}-{_OVERLAY_RENDERER[:16]}-overlay"
    else:
        key = f"{file_digest(sample.path)}-{CACHE_VERSION}-720x960-q82"
    path = CACHE_DIR / f"{key}.webp"
    with _locks[sample.id]:
        if path.is_file():
            return path
        with Image.open(sample.path) as original:
            preview = ImageOps.exif_transpose(original).convert("RGB")
        if overlay:
            from app.qa_onboarding import _render_face_overlay, _render_body_overlay

            preview.thumbnail((1200, 1200))
            renderer = _render_face_overlay if sample.kind == "face" else _render_body_overlay
            with selfit_photo._INSPECT_SEMAPHORE:
                preview = renderer(preview, {}, include_details=False)
        else:
            preview.thumbnail((720, 960))
        output = io.BytesIO()
        preview.save(output, format="WEBP", quality=86 if overlay else 82, method=4)
        _atomic_write(path, output.getvalue())
    return path


def warm_samples() -> list[dict]:
    results = []
    for sample in SAMPLES.values():
        with Image.open(sample.path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
        inspection, fingerprint = inspect_sample(sample, image)
        if not inspection.accepted or inspection.issues:
            raise RuntimeError(f"Sample {sample.id} was rejected: {inspection.issues}")
        preview = preview_path(sample)
        overlay = preview_path(sample, overlay=True)
        results.append({"id": sample.id, "fingerprint": fingerprint,
                        "originalBytes": sample.path.stat().st_size,
                        "previewBytes": preview.stat().st_size, "overlayBytes": overlay.stat().st_size})
    return results

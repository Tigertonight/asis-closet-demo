from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Iterator


ROOT_DIR = Path(__file__).resolve().parents[1]
LOCAL_USER_ID = "local_user"

_current_user_id: ContextVar[str] = ContextVar("selfit_current_user_id", default=LOCAL_USER_ID)


@dataclass(frozen=True)
class StorageContext:
    user_id: str
    user_root: Path
    upload_dir: Path
    closet_output_dir: Path
    closet_source_dir: Path
    closet_item_dir: Path
    closet_manifest_path: Path
    outfit_dir: Path
    outfit_manifest_path: Path
    tryon_record_dir: Path
    tryon_records_manifest_path: Path
    tryon_output_dir: Path
    codex_bridge_dir: Path


def sanitize_user_id(user_id: str | None) -> str:
    text = str(user_id or "").strip() or LOCAL_USER_ID
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)[:80] or LOCAL_USER_ID


def current_user_id() -> str:
    return _current_user_id.get()


@contextmanager
def user_storage(user_id: str | None) -> Iterator[None]:
    token = _current_user_id.set(sanitize_user_id(user_id))
    try:
        yield
    finally:
        _current_user_id.reset(token)


def storage_context(user_id: str | None = None) -> StorageContext:
    safe_user_id = sanitize_user_id(user_id or current_user_id())
    user_root = ROOT_DIR / "outputs" / "users" / safe_user_id
    closet_output_dir = user_root / "closet"
    tryon_output_dir = user_root / "tryon"
    return StorageContext(
        user_id=safe_user_id,
        user_root=user_root,
        upload_dir=ROOT_DIR / "uploads" / "users" / safe_user_id,
        closet_output_dir=closet_output_dir,
        closet_source_dir=closet_output_dir / "sources",
        closet_item_dir=closet_output_dir / "items",
        closet_manifest_path=closet_output_dir / "closet_manifest.json",
        outfit_dir=closet_output_dir / "outfits",
        outfit_manifest_path=closet_output_dir / "outfits_manifest.json",
        tryon_record_dir=closet_output_dir / "tryon_records",
        tryon_records_manifest_path=closet_output_dir / "tryon_records_manifest.json",
        tryon_output_dir=tryon_output_dir,
        codex_bridge_dir=tryon_output_dir / "codex_bridge",
    )


def user_asset_public_path(kind: str, path: Path, base_dir: Path) -> str:
    relative = path.relative_to(base_dir)
    return f"/user-assets/{kind}/{relative.as_posix()}"


def user_asset_disk_path(kind: str, public_path: str | None) -> Path | None:
    if not public_path:
        return None
    ctx = storage_context()
    if public_path.startswith(f"/user-assets/{kind}/"):
        relative = public_path.replace(f"/user-assets/{kind}/", "", 1)
        base = ctx.closet_output_dir if kind == "closet" else ctx.tryon_output_dir
        return base / relative
    return None


def migrate_legacy_local_user_data() -> dict[str, object]:
    ctx = storage_context(LOCAL_USER_ID)
    copied: list[str] = []
    _copy_missing(ROOT_DIR / "outputs" / "closet", ctx.closet_output_dir, copied)
    _copy_missing(ROOT_DIR / "outputs" / "tryon", ctx.tryon_output_dir, copied)
    _copy_missing(ROOT_DIR / "uploads", ctx.upload_dir, copied, skip_names={"users"})
    patched = [
        _patch_manifest_user_id(ctx.closet_manifest_path, "items"),
        _patch_manifest_user_id(ctx.outfit_manifest_path, "outfits"),
        _patch_manifest_user_id(ctx.tryon_records_manifest_path, "records"),
    ]
    return {"status": "ok", "user_id": LOCAL_USER_ID, "copied": copied, "patched_manifests": sum(1 for item in patched if item)}


def hydrate_user_from_demo_data(user_id: str) -> dict[str, object]:
    safe_user_id = sanitize_user_id(user_id)
    if safe_user_id == LOCAL_USER_ID:
        return migrate_legacy_local_user_data()

    migrate_legacy_local_user_data()
    ctx = storage_context(safe_user_id)
    local_ctx = storage_context(LOCAL_USER_ID)
    copied: list[str] = []

    _hydrate_tree(local_ctx.closet_output_dir, ctx.closet_output_dir, copied, [("closet_manifest.json", "items"), ("outfits_manifest.json", "outfits"), ("tryon_records_manifest.json", "records")], safe_user_id)
    _hydrate_tree(local_ctx.tryon_output_dir, ctx.tryon_output_dir, copied, [], safe_user_id)
    _hydrate_tree(local_ctx.upload_dir, ctx.upload_dir, copied, [], safe_user_id)

    return {"status": "ok", "user_id": safe_user_id, "copied": copied}


def _copy_missing(source: Path, target: Path, copied: list[str], skip_names: set[str] | None = None) -> None:
    if not source.exists():
        return
    skip_names = skip_names or set()
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in skip_names:
            continue
        dest = target / item.name
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            _copy_missing(item, dest, copied, skip_names)
        elif not dest.exists():
            shutil.copy2(item, dest)
            copied.append(str(dest))


def _patch_manifest_user_id(path: Path, collection_key: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    collection = data.get(collection_key)
    if not isinstance(collection, list):
        return False
    changed = False
    for item in collection:
        if isinstance(item, dict) and not item.get("user_id"):
            item["user_id"] = LOCAL_USER_ID
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def _hydrate_tree(source: Path, target: Path, copied: list[str], manifests: list[tuple[str, str]], user_id: str) -> None:
    if not source.exists():
        return
    _copy_missing(source, target, copied)
    for filename, collection_key in manifests:
        manifest = target / filename
        source_manifest = source / filename
        if _manifest_has_items(manifest, collection_key):
            _patch_manifest_user_id_to(manifest, collection_key, user_id)
            continue
        if source_manifest.exists():
            shutil.copy2(source_manifest, manifest)
            copied.append(str(manifest))
            _patch_manifest_user_id_to(manifest, collection_key, user_id)


def _manifest_has_items(path: Path, collection_key: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(data.get(collection_key))


def _patch_manifest_user_id_to(path: Path, collection_key: str, user_id: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    collection = data.get(collection_key)
    if not isinstance(collection, list):
        return False
    changed = False
    for item in collection:
        if isinstance(item, dict) and item.get("user_id") != user_id:
            item["user_id"] = user_id
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed

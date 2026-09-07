"""管理后台：内置图片素材库（selfit content_v2）清单接口。

数据口径：
- 素材根目录 app/static/selfit/assets/content_v2/，随代码入库（git = 代码）；
- 三类素材：{人格}/garments 单品图、{人格}/outfits 穿搭图、layouts/ 统一排版图；
- 排版图的人格与件数信息来自同名 .qa.json 的 placements，其余类别从文件名解析；
- 清单构建需读 3000+ 个 qa.json，进程内缓存：目录树指纹（max mtime + 文件数）变化才重建。

鉴权：与 /admin/api/analytics 同级，走 get_admin_user。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import get_admin_user

router = APIRouter(prefix="/admin/api/assets", tags=["selfit-admin-assets"])

CONTENT_V2_DIR = Path(__file__).resolve().parent / "static" / "selfit" / "assets" / "content_v2"
IMAGE_SUFFIXES = {".webp", ".png", ".jpg", ".jpeg"}

# 清单缓存：{fingerprint, manifest}
_cache: dict[str, Any] = {"fingerprint": None, "manifest": None}
_cache_lock = threading.Lock()


def _dir_fingerprint() -> tuple[int, int]:
    """目录树指纹：全部图片/qa.json 的数量与最新 mtime，扫描本身不读文件内容。"""

    latest = 0
    count = 0
    for path in CONTENT_V2_DIR.rglob("*"):
        if path.suffix.lower() not in IMAGE_SUFFIXES and path.suffix != ".json":
            continue
        count += 1
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            continue
        if mtime > latest:
            latest = mtime
    return latest, count


def _read_qa(image: Path) -> dict[str, Any] | None:
    qa_path = image.parent / (image.stem + ".qa.json")
    if not qa_path.exists():
        return None
    try:
        return json.loads(qa_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_manifest() -> dict[str, Any]:
    personas: list[str] = []
    garments: list[dict[str, Any]] = []
    outfits: list[dict[str, Any]] = []
    layouts: list[dict[str, Any]] = []

    for entry in sorted(CONTENT_V2_DIR.iterdir()):
        if not entry.is_dir() or entry.name == "layouts":
            continue
        persona = entry.name
        personas.append(persona)

        garments_dir = entry / "garments"
        if garments_dir.is_dir():
            for image in sorted(garments_dir.iterdir()):
                if image.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                # 文件名约定：{persona}-{category}-{序号}-{版本}
                parts = image.stem.split("-")
                category = parts[1] if len(parts) >= 3 and parts[0] == persona else "other"
                garments.append({
                    "name": image.stem,
                    "url": f"/static/selfit/assets/content_v2/{persona}/garments/{image.name}",
                    "persona": persona,
                    "category": category,
                })

        outfits_dir = entry / "outfits"
        if outfits_dir.is_dir():
            for image in sorted(outfits_dir.iterdir()):
                if image.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                # 文件名约定：outfit_{persona}_master_{编号}[_{版本}]
                parts = image.stem.split("_")
                master = parts[3] if len(parts) > 3 else ""
                version = parts[4] if len(parts) > 4 else "base"
                outfits.append({
                    "name": image.stem,
                    "url": f"/static/selfit/assets/content_v2/{persona}/outfits/{image.name}",
                    "persona": persona,
                    "master": master,
                    "version": version,
                })

    layouts_root = CONTENT_V2_DIR / "layouts"
    if layouts_root.is_dir():
        for layout_dir in sorted(layout_root for layout_root in layouts_root.iterdir() if layout_root.is_dir()):
            for image in sorted(layout_dir.iterdir()):
                if image.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                item: dict[str, Any] = {
                    "name": image.stem,
                    "url": f"/static/selfit/assets/content_v2/layouts/{layout_dir.name}/{image.name}",
                    "layout": layout_dir.name,
                    "personas": [],
                    "slots": [],
                    "count": 0,
                }
                qa = _read_qa(image)
                if qa:
                    placements = qa.get("placements", [])
                    item["count"] = len(placements)
                    item["slots"] = [str(p.get("slot", "")) for p in placements]
                    placement_personas = set()
                    for placement in placements:
                        # garment_id 形如 garment_{persona}_{category}_{序号}
                        ids = str(placement.get("garment_id", "")).split("_")
                        if len(ids) >= 2 and ids[0] == "garment":
                            placement_personas.add(ids[1])
                    item["personas"] = sorted(placement_personas)
                layouts.append(item)

    return {
        "personas": personas,
        "garments": garments,
        "outfits": outfits,
        "layouts": layouts,
    }


def _get_manifest() -> dict[str, Any]:
    fingerprint = _dir_fingerprint()
    with _cache_lock:
        if _cache["fingerprint"] == fingerprint and _cache["manifest"] is not None:
            return _cache["manifest"]
    manifest = _build_manifest()
    with _cache_lock:
        # 双重检查：并发请求可能已用相同指纹填好缓存
        if _cache["fingerprint"] != fingerprint:
            _cache["fingerprint"] = fingerprint
            _cache["manifest"] = manifest
        return _cache["manifest"]


@router.get("/manifest")
async def assets_manifest(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    return JSONResponse(
        content=_get_manifest(),
        headers={"Cache-Control": "no-store"},
    )

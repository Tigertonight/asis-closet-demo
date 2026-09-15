"""管理后台：照片算法版本注册表的查询 / 对比 / 重算接口。

与 /admin/api/submissions 同一鉴权级别（get_admin_user）。
只做数据查询与后台任务触发，跑批在 photo_algorithm_registry 的串行
executor 里执行，不会阻塞请求线程。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app import photo_algorithm_registry as registry
from app.auth import get_admin_user

router = APIRouter(prefix="/admin/api/photo-algorithms", tags=["photo-algorithm-registry"])


@router.get("")
def list_photo_algorithms(_: dict[str, Any] = Depends(get_admin_user)) -> dict[str, Any]:
    """版本列表：算法快照元信息 + 各版本报告统计（标签分布）。"""
    return {"versions": registry.list_versions(), "current": registry.current_version()}


@router.get("/compare")
def compare_photo_algorithms(
    version_a: str = Query(alias="from"),
    version_b: str = Query(alias="to"),
    _: dict[str, Any] = Depends(get_admin_user),
) -> dict[str, Any]:
    """任意两版本报告 diff：标签变化矩阵 + 逐照片明细。"""
    try:
        return registry.compare_reports(version_a, version_b)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{version}/photos")
def list_photo_algorithm_report(
    version: str,
    label: str | None = None,
    changed_from: str | None = None,
    _: dict[str, Any] = Depends(get_admin_user),
) -> dict[str, Any]:
    """单个版本的报告明细（可按标签筛选；changed_from 给出时只看两版本间变化的照片）。"""
    if not (registry.ALGORITHM_DIR / version / "manifest.json").exists():
        raise HTTPException(status_code=404, detail=f"算法版本未注册: {version}")
    rows = registry._load_report_rows(version)
    items = [rows[key] for key in sorted(rows)]
    if label:
        items = [
            row
            for row in items
            if label in {
                (row.get("skin") or {}).get("label"),
                (row.get("face") or {}).get("label"),
                (row.get("body") or {}).get("label"),
            }
        ]
    if changed_from:
        diff = registry.compare_reports(changed_from, version)
        changed_ids = {detail["photo_id"] for detail in diff["details"]}
        items = [row for row in items if row["photo_id"] in changed_ids]
    return {"version": version, "count": len(items), "photos": items}


@router.post("/{version}/rerun")
def rerun_photo_algorithm_report(
    version: str,
    payload: dict[str, Any] = Body(default={}),
    _: dict[str, Any] = Depends(get_admin_user),
) -> dict[str, Any]:
    """手动触发该版本全量跑批（force 可选，默认覆盖重算）。"""
    force = bool(payload.get("force", True))
    if not registry.submit_rerun(version, force=force):
        raise HTTPException(status_code=404, detail=f"算法版本未注册: {version}")
    return {"queued": True, "version": version, "force": force}

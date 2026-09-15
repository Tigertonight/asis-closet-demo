"""照片算法版本注册表：历史算法快照 + 全量照片诊断存档 + 任意版本对比/重算。

背景（2026-09 肤色事故复盘）：算法迭代后无法回答「旧版本对这批照片怎么判的」、
「新版到底改了哪些照片的结果」。本模块把算法代码本身版本化存档（代码即真相，
不依赖 git 历史在服务器上可用），版本变化后对全量存量照片跑批存诊断报告：

- 任意两个版本的报告 diff（标签变化矩阵 + 每张照片的明细）；
- 任意版本对任意照片重算（新照片上传后异步补跑所有历史版本）；
- 用户报告 / session 照片带 algorithm_version，历史问题可复现。

存储（数据目录，随服务器备份，不进 git）：

    outputs/photo_algorithms/<version>/
        attribute_pipeline.py   # 当时 app/attribute_pipeline.py 的完整拷贝
        cv_pipeline.py          # 当时 app/cv_pipeline.py 的完整拷贝
        manifest.json           # {version, created_at, note}
    outputs/photo_algorithm_reports/<version>/
        reports.jsonl           # 每照片一行诊断（photo_id 去重，重跑覆盖）
        manifest.json           # 跑批元信息 + 标签分布统计

photo_id 口径（稳定标识）：
- 用户照片：asset_{kind}_{sha12}（内容寻址，跨会话唯一）
- QA 素材：qa:{manifest 相对路径}

加载任意版本的实现要点：快照目录存原始文件（复现保真），加载时在内存里把
attribute_pipeline 源码的 `from app.cv_pipeline import` 重写到快照版 cv_pipeline
的动态模块名，再 exec；mediapipe 模型路径常量统一 patch 到当前 app/models
（模型文件跨版本不变）。每个版本模块进程内缓存一次。
"""

from __future__ import annotations

import importlib.util
import json
import re
import secrets
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from app.storage import ROOT_DIR

ALGORITHM_DIR = ROOT_DIR / "outputs" / "photo_algorithms"
REPORT_DIR = ROOT_DIR / "outputs" / "photo_algorithm_reports"

_CURRENT_SOURCE = Path(__file__).resolve().parent / "attribute_pipeline.py"
_CV_SOURCE = Path(__file__).resolve().parent / "cv_pipeline.py"
_MODELS_DIR = Path(__file__).resolve().parent / "models"

# 串行跑批：诊断是低优先级后台任务，不与用户请求抢 CPU
_REGISTRY_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photo-algo-registry")
_WRITE_LOCK = threading.Lock()
_LOADED_MODULES: dict[str, types.ModuleType] = {}
_LOAD_LOCK = threading.Lock()

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9._-]+$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 快照与版本清单
# ---------------------------------------------------------------------------

def current_version() -> str:
    """当前代码的照片算法版本号（app.attribute_pipeline.PHOTO_ALGORITHM_VERSION）。"""
    from app.attribute_pipeline import PHOTO_ALGORITHM_VERSION

    return str(PHOTO_ALGORITHM_VERSION)


def snapshot_current(note: str = "") -> str:
    """把当前算法代码快照存档；版本目录已存在则幂等跳过（返回版本号）。

    快照 = attribute_pipeline.py + cv_pipeline.py 的字节级拷贝。
    历史版本（git 检出前）无法凭空生成：只有运行过该版本的服务才会留下快照。
    """
    version = current_version()
    if not _SAFE_VERSION.match(version):
        raise ValueError(f"非法版本号: {version}")
    target = ALGORITHM_DIR / version
    manifest_path = target / "manifest.json"
    with _WRITE_LOCK:
        if manifest_path.exists():
            return version
        target.mkdir(parents=True, exist_ok=True)
        (target / "attribute_pipeline.py").write_bytes(_CURRENT_SOURCE.read_bytes())
        (target / "cv_pipeline.py").write_bytes(_CV_SOURCE.read_bytes())
        manifest = {
            "version": version,
            "created_at": _now_iso(),
            "note": note,
            "source": "auto_snapshot_on_version_change",
        }
        _atomic_write_json(manifest_path, manifest)
    return version


def list_versions() -> list[dict[str, Any]]:
    """全部已注册版本：算法快照元信息 + 报告统计（有报告才带 stats）。"""
    versions: list[dict[str, Any]] = []
    if ALGORITHM_DIR.is_dir():
        for entry in sorted(ALGORITHM_DIR.iterdir(), reverse=True):
            if not entry.is_dir() or not _SAFE_VERSION.match(entry.name):
                continue
            manifest = _read_json(entry / "manifest.json") or {}
            item = {
                "version": entry.name,
                "created_at": manifest.get("created_at"),
                "note": manifest.get("note") or "",
                "is_current": entry.name == current_version(),
                **_report_stats(entry.name),
            }
            versions.append(item)
    return versions


# ---------------------------------------------------------------------------
# 加载任意版本（import 重写 + 模型路径 patch）
# ---------------------------------------------------------------------------

def load_algorithm(version: str) -> types.ModuleType:
    """加载指定版本的算法模块（analyze_face_photo / analyze_body_photo 可直接调用）。

    - cv_pipeline 快照用 importlib 标准加载（唯一模块名，与当前 app.cv_pipeline 隔离）；
    - attribute_pipeline 快照在内存里把 `from app.cv_pipeline import` 重写到
      快照版 cv 模块名后 exec（快照文件保持原始字节，复现保真）；
    - mediapipe 模型常量 patch 到当前 app/models（模型跨版本不变）；
    - 每版本进程内缓存；加载失败抛 ValueError（版本不存在/代码损坏）。
    """
    with _LOAD_LOCK:
        module = _LOADED_MODULES.get(version)
        if module is not None:
            return module
        if not _SAFE_VERSION.match(version):
            raise ValueError(f"非法版本号: {version}")
        snap_dir = ALGORITHM_DIR / version
        if not snap_dir.is_dir():
            raise ValueError(f"算法版本未注册: {version}")
        cv_path = snap_dir / "cv_pipeline.py"
        ap_path = snap_dir / "attribute_pipeline.py"
        if not cv_path.is_file() or not ap_path.is_file():
            raise ValueError(f"算法快照不完整: {version}")

        suffix = re.sub(r"[^0-9A-Za-z_]", "_", version)
        cv_module_name = f"_photo_algo_snapshot_cv_{suffix}"
        cv_spec = importlib.util.spec_from_file_location(cv_module_name, cv_path)
        cv_module = importlib.util.module_from_spec(cv_spec)
        sys.modules[cv_module_name] = cv_module
        cv_spec.loader.exec_module(cv_module)
        # 模型路径 patch：快照里的 Path(__file__) 指向 outputs 快照目录，无 models
        for attr, filename in (
            ("FACE_DETECTOR_MODEL", "blaze_face_short_range.tflite"),
            ("FACE_LANDMARKER_MODEL", "face_landmarker.task"),
        ):
            if hasattr(cv_module, attr):
                setattr(cv_module, attr, _MODELS_DIR / filename)

        ap_module_name = f"_photo_algo_snapshot_ap_{suffix}"
        source = ap_path.read_text(encoding="utf-8")
        if "from app.cv_pipeline import" in source:
            source = source.replace("from app.cv_pipeline import", f"from {cv_module_name} import")
        if re.search(r"^\s*from app\.", source, flags=re.MULTILINE):
            raise ValueError(f"快照 {version} 存在未支持的 app.* 依赖，无法加载")

        ap_module = types.ModuleType(ap_module_name)
        ap_module.__file__ = str(ap_path)
        sys.modules[ap_module_name] = ap_module
        exec(compile(source, str(ap_path), "exec"), ap_module.__dict__)
        for attr, filename in (
            ("POSE_LANDMARKER_MODEL", "pose_landmarker_lite.task"),
            ("SELFIE_SEGMENTER_MODEL", "selfie_segmenter.tflite"),
        ):
            if hasattr(ap_module, attr):
                setattr(ap_module, attr, _MODELS_DIR / filename)

        _LOADED_MODULES[version] = ap_module
        return ap_module


# ---------------------------------------------------------------------------
# 存量照片清单（用户 accepted/rejected + QA 素材）
# ---------------------------------------------------------------------------

def iter_all_photos() -> list[dict[str, Any]]:
    """全量存量照片，统一结构（按 photo_id 排序，跑批与对比的公共口径）：

    {photo_id, path, kind, source, user_id, session_id, original_status}
    - source: user（含 rejected 留存）| qa（标注素材）
    - original_status: accepted | rejected | qa
    """
    from app import selfit_onboarding

    photos: dict[str, dict[str, Any]] = {}

    # 1) 归属索引：asset_id -> (user_id, session_id, status)
    ownership: dict[str, dict[str, Any]] = {}
    try:
        data = selfit_onboarding._load_store()
    except Exception:
        data = {}
    for record in data.get("sessions") or []:
        session_id = str(record.get("session_id") or "")
        user_id = str(record.get("user_id") or "") or None
        for kind, photo in (record.get("photos") or {}).items():
            asset_id = str(photo.get("asset_id") or "")
            if asset_id:
                ownership[asset_id] = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "original_status": str(photo.get("status") or ""),
                }
    for item in data.get("rejected_photos") or []:
        asset_id = str(item.get("asset_id") or "")
        if asset_id and asset_id not in ownership:
            ownership[asset_id] = {
                "user_id": str(item.get("user_id") or "") or None,
                "session_id": str(item.get("session_id") or "") or None,
                "original_status": "rejected",
            }

    # 2) 用户照片资产（asset 只增不删，含被拒留存）。
    #    严格匹配 asset_{kind}_{sha12}：排除叠加层渲染生成的 *_analysis-v1.* 衍生副本
    assets_dir = Path(selfit_onboarding.SELFIT_ONBOARDING_DIR) / "assets"
    asset_pattern = re.compile(r"^asset_(face|body)_[0-9a-f]{12}$")
    if assets_dir.is_dir():
        for asset_file in assets_dir.glob("*/*"):
            if not asset_file.is_file():
                continue
            asset_id = asset_file.stem
            match = asset_pattern.match(asset_id)
            if not match:
                continue
            kind = match.group(1)
            meta = ownership.get(asset_id) or {
                "user_id": None,
                "session_id": asset_file.parent.name,
                "original_status": "unknown",
            }
            photos[asset_id] = {
                "photo_id": asset_id,
                "path": str(asset_file),
                "kind": kind,
                "source": "user",
                "user_id": meta["user_id"],
                "session_id": meta["session_id"],
                "original_status": meta["original_status"],
            }

    # 3) QA 标注素材（含用户照片归档副本）
    qa_manifest = ROOT_DIR / "qa_photos" / "manifest.json"
    manifest_items = _read_json(qa_manifest) or []
    for entry in manifest_items:
        rel = str(entry.get("file") or "")
        if not rel:
            continue
        path = ROOT_DIR / "qa_photos" / rel
        if not path.is_file():
            continue
        photos[f"qa:{rel}"] = {
            "photo_id": f"qa:{rel}",
            "path": str(path),
            "kind": str(entry.get("kind") or ("face" if "/face" in rel else "body")),
            "source": "qa",
            "user_id": None,
            "session_id": None,
            "original_status": "qa",
        }

    return [photos[key] for key in sorted(photos)]


# ---------------------------------------------------------------------------
# 诊断报告跑批
# ---------------------------------------------------------------------------

def analyze_photo_with(version: str, photo: dict[str, Any]) -> dict[str, Any]:
    """用指定版本算法分析单张照片 → 报告行（reports.jsonl 的一行）。

    照片读取失败/算法异常不抛出（报告行记 error），保证跑批不中断。
    """
    row: dict[str, Any] = {
        "photo_id": photo["photo_id"],
        "kind": photo["kind"],
        "source": photo.get("source"),
        "user_id": photo.get("user_id"),
        "session_id": photo.get("session_id"),
        "original_status": photo.get("original_status"),
        "algorithm_version": version,
        "analyzed_at": _now_iso(),
    }
    try:
        module = load_algorithm(version)
        image = Image.open(photo["path"])
        if photo["kind"] == "body":
            result = module.analyze_body_photo(image)
        else:
            result = module.analyze_face_photo(image)
        attributes = result.get("attributes") or {}
        row["status"] = result.get("status")
        row["confidence"] = result.get("confidence")
        row["issues"] = [str(item.get("code") or "") for item in result.get("issues") or []]
        for attr_name in ("skin_tone", "face_shape", "body_shape"):
            attr = attributes.get(attr_name) or {}
            if not attr:
                continue
            key = attr_name.replace("_tone", "").replace("_shape", "")
            row[key] = {
                "label": attr.get("label"),
                "confidence": attr.get("confidence"),
                "status": attr.get("status"),
                "issues": [str(item.get("code") or "") for item in attr.get("issues") or []],
                "l_star": (attr.get("evidence") or {}).get("l_star"),
                "raw_l_star": (attr.get("evidence") or {}).get("raw_l_star"),
                "ita_deg": (attr.get("evidence") or {}).get("ita_deg"),
            }
    except Exception as exc:  # noqa: BLE001 - 单张失败不中断跑批
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["status"] = "error"
    return row


def _report_paths(version: str) -> tuple[Path, Path]:
    directory = REPORT_DIR / version
    return directory / "reports.jsonl", directory / "manifest.json"


def _load_report_rows(version: str) -> dict[str, dict[str, Any]]:
    reports_path, _ = _report_paths(version)
    rows: dict[str, dict[str, Any]] = {}
    if reports_path.is_file():
        for line in reports_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("photo_id"):
                rows[str(row["photo_id"])] = row
    return rows


def _save_report_rows(version: str, rows: dict[str, dict[str, Any]]) -> None:
    reports_path, manifest_path = _report_paths(version)
    reports_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [rows[key] for key in sorted(rows)]
    tmp_path = reports_path.with_name(f"{reports_path.name}.{secrets.token_urlsafe(6)}.tmp")
    tmp_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered),
        encoding="utf-8",
    )
    tmp_path.replace(reports_path)
    _atomic_write_json(manifest_path, _build_report_manifest(version, ordered))


def _build_report_manifest(version: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    label_stats: dict[str, dict[str, int]] = {}
    for row in rows:
        kind = str(row.get("kind") or "face")
        bucket = label_stats.setdefault(kind, {})
        if row.get("error"):
            bucket["<error>"] = bucket.get("<error>", 0) + 1
            continue
        skin = row.get("skin") or {}
        face = row.get("face") or {}
        body = row.get("body") or {}
        for prefix, attr in (("skin:", skin), ("face:", face), ("body:", body)):
            label = attr.get("label")
            if label:
                bucket[f"{prefix}{label}"] = bucket.get(f"{prefix}{label}", 0) + 1
    return {
        "version": version,
        "generated_at": _now_iso(),
        "photo_count": len(rows),
        "error_count": sum(1 for row in rows if row.get("error")),
        "label_stats": label_stats,
    }


def _report_stats(version: str) -> dict[str, Any]:
    reports_path, _ = _report_paths(version)
    if not reports_path.is_file():
        return {"report_generated_at": None, "report_photo_count": 0, "report_label_stats": {}}
    rows = _load_report_rows(version)
    manifest = _build_report_manifest(version, list(rows.values()))
    return {
        "report_generated_at": manifest["generated_at"],
        "report_photo_count": manifest["photo_count"],
        "report_error_count": manifest["error_count"],
        "report_label_stats": manifest["label_stats"],
    }


def run_report(version: str, photo_ids: Iterable[str] | None = None, force: bool = False) -> dict[str, Any]:
    """跑批写报告：指定版本 × 照片集（默认全量），按 photo_id 覆盖旧结果。

    force=False 时跳过已有结果（重跑增量）；返回本次跑批摘要。
    """
    snapshot_current()  # 保证当前版本有快照（历史版本目录必须已存在）
    if not (ALGORITHM_DIR / version).is_dir():
        raise ValueError(f"算法版本未注册: {version}")
    photos = iter_all_photos()
    if photo_ids is not None:
        wanted = set(photo_ids)
        photos = [photo for photo in photos if photo["photo_id"] in wanted]
    with _WRITE_LOCK:
        rows = {} if force else _load_report_rows(version)
    analyzed = skipped = failed = 0
    for photo in photos:
        if not force and photo["photo_id"] in rows:
            skipped += 1
            continue
        row = analyze_photo_with(version, photo)
        if row.get("error"):
            failed += 1
        else:
            analyzed += 1
        with _WRITE_LOCK:
            rows[photo["photo_id"]] = row
            _save_report_rows(version, rows)
    return {
        "version": version,
        "total": len(photos),
        "analyzed": analyzed,
        "skipped": skipped,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# 版本对比
# ---------------------------------------------------------------------------

def compare_reports(version_a: str, version_b: str) -> dict[str, Any]:
    """任意两版本报告 diff：标签变化矩阵 + 逐照片明细。

    属性口径：skin / face / body 三类，任一 label 变化即记入变化明细；
    L* 变化超过 1 也单独标记（肤色事故这类「同标签不同读数」的场景）。
    """
    for version in (version_a, version_b):
        if not (ALGORITHM_DIR / version / "manifest.json").exists():
            raise ValueError(f"算法版本未注册: {version}")
    rows_a = _load_report_rows(version_a)
    rows_b = _load_report_rows(version_b)
    common_ids = sorted(set(rows_a) & set(rows_b))

    label_matrix: dict[str, dict[str, int]] = {}
    details: list[dict[str, Any]] = []
    for photo_id in common_ids:
        row_a, row_b = rows_a[photo_id], rows_b[photo_id]
        changes: list[str] = []
        label_pairs: list[str] = []
        for key in ("skin", "face", "body"):
            attr_a = row_a.get(key) or {}
            attr_b = row_b.get(key) or {}
            if not attr_a and not attr_b:
                continue
            label_a = attr_a.get("label") or "—"
            label_b = attr_b.get("label") or "—"
            if label_a != label_b:
                changes.append(key)
                bucket = label_matrix.setdefault(key, {})
                pair = f"{label_a} → {label_b}"
                bucket[pair] = bucket.get(pair, 0) + 1
                label_pairs.append(pair)
            elif key == "skin":
                l_a = attr_a.get("l_star")
                l_b = attr_b.get("l_star")
                if isinstance(l_a, (int, float)) and isinstance(l_b, (int, float)):
                    if abs(float(l_b) - float(l_a)) >= 1.0:
                        changes.append("skin_l_star")
        issues_a = set(row_a.get("issues") or [])
        issues_b = set(row_b.get("issues") or [])
        new_issues = sorted(issues_b - issues_a)
        if new_issues:
            changes.append("issues")
        if not changes:
            continue
        details.append(
            {
                "photo_id": photo_id,
                "kind": row_b.get("kind"),
                "source": row_b.get("source"),
                "user_id": row_b.get("user_id"),
                "session_id": row_b.get("session_id"),
                "changes": changes,
                "label_pairs": label_pairs,
                "new_issues": new_issues,
                "a": _compact_row(rows_a[photo_id]),
                "b": _compact_row(rows_b[photo_id]),
            }
        )

    return {
        "from": version_a,
        "to": version_b,
        "from_count": len(rows_a),
        "to_count": len(rows_b),
        "common": len(common_ids),
        "only_in_from": sorted(set(rows_a) - set(rows_b)),
        "only_in_to": sorted(set(rows_b) - set(rows_a)),
        "changed": len(details),
        "label_matrix": label_matrix,
        "details": details,
    }


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": row.get("status"),
        "confidence": row.get("confidence"),
        "issues": row.get("issues") or [],
        "error": row.get("error"),
        **{
            key: {
                "label": (row.get(key) or {}).get("label"),
                "l_star": (row.get(key) or {}).get("l_star"),
                "raw_l_star": (row.get(key) or {}).get("raw_l_star"),
            }
            for key in ("skin", "face", "body")
            if row.get(key)
        },
    }


# ---------------------------------------------------------------------------
# 自动化：版本变化 → 快照 + 全量跑批；新照片 → 异步补跑所有版本
# ---------------------------------------------------------------------------

def ensure_current_version_async(note: str = "") -> None:
    """当前版本无快照时：快照 + 后台全量跑批（幂等，不阻塞调用方）。

    服务启动与新照片上传后都可调用；已有快照则什么都不做。
    """
    version = current_version()
    if (ALGORITHM_DIR / version / "manifest.json").exists():
        return
    _REGISTRY_EXECUTOR.submit(_ensure_current_sync, version, note)


def _ensure_current_sync(version: str, note: str) -> None:
    try:
        snapshot_current(note)
        run_report(version)
    except Exception:
        pass  # 注册表是旁路能力，故障不影响主服务


def record_photo_async(photo: dict[str, Any]) -> None:
    """新照片异步补跑：对所有已注册版本各算一次并写进该版本报告。

    调用方（照片上传链路）传入 iter_all_photos 的同构条目；失败静默
    （主流程已经用当前版本算过，注册表缺一张历史报告不影响用户）。
    """
    _REGISTRY_EXECUTOR.submit(_record_photo_sync, photo)


def _record_photo_sync(photo: dict[str, Any]) -> None:
    try:
        for version in [item["version"] for item in list_versions()]:
            if not (ALGORITHM_DIR / version / "manifest.json").exists():
                continue
            row = analyze_photo_with(version, photo)
            with _WRITE_LOCK:
                rows = _load_report_rows(version)
                rows[photo["photo_id"]] = row
                _save_report_rows(version, rows)
    except Exception:
        pass


def submit_rerun(version: str, force: bool = True) -> bool:
    """管理后台手动触发跑批（后台执行，立即返回）。版本未注册返回 False。"""
    if not (ALGORITHM_DIR / version / "manifest.json").exists():
        return False

    def _job() -> None:
        try:
            run_report(version, force=force)
        except Exception:
            pass

    _REGISTRY_EXECUTOR.submit(_job)
    return True


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{secrets.token_urlsafe(6)}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)

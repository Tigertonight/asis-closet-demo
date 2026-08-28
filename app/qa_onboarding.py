"""onboarding 属性识别算法的 QA 目检页面。

路由：`GET /qa/onboarding-attributes`（内部 QA 用，不对 C 端暴露）。
素材：`qa_photos/{face,body}/*.jpg` + `manifest.json`（来源溯源，见
scripts/collect_onboarding_qa_photos.py）。

分析结果按「文件 + mtime」缓存到 `qa_photos/_results.json`；
`?refresh=1` 强制全量重算。
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from PIL import Image, ImageDraw, ImageFont

from app.auth import admin_token_from_request, resolve_admin_user

from app.attribute_pipeline import (
    BODY_SHAPE_LABELS,
    FACE_SHAPE_LABELS,
    SKIN_TONE_LABELS,
    analyze_body_photo,
    analyze_face_photo,
    debug_body_geometry,
    debug_face_geometry,
)
from app.storage import ROOT_DIR

QA_PHOTO_DIR = ROOT_DIR / "qa_photos"
QA_RESULTS_CACHE = QA_PHOTO_DIR / "_results.json"
QA_OVERLAY_DIR = QA_PHOTO_DIR / "_overlays"
QA_ANNOTATIONS_PATH = QA_PHOTO_DIR / "_annotations.json"
OVERLAY_VERSION = "v1"  # 叠加层绘制逻辑变更时递增，触发重画
UPLOAD_MAX_BYTES = 12 * 1024 * 1024
UPLOAD_MAX_SIDE = 1600

router = APIRouter(tags=["qa-onboarding"])

ATTRIBUTE_LABELS = {"skin_tone": "肤色", "face_shape": "脸型", "body_shape": "身型"}
STATUS_LABELS = {"pass": "通过", "warn": "存疑", "fail": "拒绝", "unknown": "未识别"}


def _load_manifest() -> list[dict[str, Any]]:
    path = QA_PHOTO_DIR / "manifest.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(items: list[dict[str, Any]]) -> None:
    QA_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    (QA_PHOTO_DIR / "manifest.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cache() -> dict[str, Any]:
    if QA_RESULTS_CACHE.exists():
        try:
            return json.loads(QA_RESULTS_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _analyze_all(refresh: bool = False) -> list[dict[str, Any]]:
    cache = {} if refresh else _load_cache()
    entries = []
    for item in _load_manifest():
        path = QA_PHOTO_DIR / item["file"]
        if not path.exists():
            continue
        mtime = path.stat().st_mtime
        cached = cache.get(item["file"])
        if cached and cached.get("mtime") == mtime:
            result = cached["result"]
        else:
            with Image.open(path) as image:
                image = image.convert("RGB")
                result = analyze_face_photo(image) if item["kind"] == "face" else analyze_body_photo(image)
            cache[item["file"]] = {"mtime": mtime, "result": result}
        entries.append({"item": item, "result": result})
    QA_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    QA_RESULTS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return entries


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# 数据标注：多任务、逐属性标注、一键对比
# ---------------------------------------------------------------------------

# 每种照片可标注的属性（属性 key、中文名、可选值）
ANNOTATION_SCHEMA: dict[str, list[tuple[str, str, list[str]]]] = {
    "face": [("skin_tone", "肤色", SKIN_TONE_LABELS), ("face_shape", "脸型", FACE_SHAPE_LABELS)],
    "body": [("body_shape", "身型", BODY_SHAPE_LABELS)],
}


def _load_annotations() -> dict[str, Any]:
    if QA_ANNOTATIONS_PATH.exists():
        try:
            data = json.loads(QA_ANNOTATIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tasks"), list):
                return data
        except json.JSONDecodeError:
            pass
    return {"tasks": []}


def _save_annotations(data: dict[str, Any]) -> None:
    QA_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    QA_ANNOTATIONS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_annotation_task(data: dict[str, Any], task_id: str | None) -> dict[str, Any] | None:
    tasks = data.get("tasks", [])
    if task_id:
        return next((task for task in tasks if task.get("id") == task_id), None)
    return tasks[-1] if tasks else None


def _annotation_stats(task: dict[str, Any] | None, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """标注覆盖率 + 与算法结果的一致/不一致计数。"""
    stats = {"annotated_files": 0, "total_files": len(entries), "annotated_attrs": 0, "agree": 0, "disagree": 0}
    if not task:
        return stats
    annotations = task.get("annotations") or {}
    label_by_file = {
        entry["item"]["file"]: {name: attr.get("label") for name, attr in (entry["result"].get("attributes") or {}).items()}
        for entry in entries
    }
    for file, attrs in annotations.items():
        if not attrs:
            continue
        stats["annotated_files"] += 1
        for attr_name, value in attrs.items():
            if not value:
                continue
            stats["annotated_attrs"] += 1
            algo_label = (label_by_file.get(file) or {}).get(attr_name)
            if algo_label is None:
                continue  # 算法未识别，不参与一致率
            if algo_label == value:
                stats["agree"] += 1
            else:
                stats["disagree"] += 1
    return stats


def _annotation_card(entry: dict[str, Any], task: dict[str, Any], overlays: dict[str, str], diff_only: bool) -> str | None:
    item, result = entry["item"], entry["result"]
    file = item["file"]
    annotations = (task.get("annotations") or {}).get(file) or {}
    algo_labels = {name: attr.get("label") for name, attr in (result.get("attributes") or {}).items()}
    algo_conf = {name: attr.get("confidence", 0.0) for name, attr in (result.get("attributes") or {}).items()}

    groups_html = []
    has_diff = False
    for attr_name, attr_label, options in ANNOTATION_SCHEMA.get(item["kind"], []):
        selected = annotations.get(attr_name, "")
        algo = algo_labels.get(attr_name)
        if selected and algo and selected != algo:
            has_diff = True
        buttons = "".join(
            f'<button type="button" class="anno-opt{" is-sel" if selected == option else ""}" '
            f'data-file="{_esc(file)}" data-attr="{_esc(attr_name)}" data-value="{_esc(option)}">{_esc(option)}</button>'
            for option in options
        )
        diff_badge = f'<span class="diff-badge">算法：{_esc(algo)} ≠ 标注：{_esc(selected)}</span>' if selected and algo and selected != algo else ""
        groups_html.append(
            f'<div class="anno-group{" is-diff" if selected and algo and selected != algo else ""}" '
            f'data-saved="{_esc(selected)}" data-attr-name="{_esc(attr_name)}">'
            f'<div class="anno-group-head"><span>{_esc(attr_label)}</span>'
            f'<small>算法：{_esc(algo or "未识别")}{f" {int(round(algo_conf.get(attr_name, 0.0) * 100))}%" if algo else ""}</small></div>'
            f'<div class="anno-options">{buttons}</div>{diff_badge}</div>'
        )
    if diff_only and not has_diff:
        return None

    overlay = overlays.get(file)
    thumb_src = f"/qa-photos/{_esc(overlay)}" if overlay else f"/qa-photos/{_esc(file)}"
    return f"""
    <article class="card anno-card{" card--diff" if has_diff else ""}">
      <div class="thumb"><img loading="lazy" src="{thumb_src}" alt="{_esc(file)}" /></div>
      <div class="card-body">
        <div class="card-head"><b>{_esc(file)}</b></div>
        {"".join(groups_html)}
      </div>
    </article>
    """


def _annotate_list_content(entries: list[dict[str, Any]]) -> str:
    """标注任务列表：统计概览 + 详情入口 + 新建。"""
    data = _load_annotations()
    rows = []
    for task in reversed(data.get("tasks", [])):
        stats = _annotation_stats(task, entries)
        rows.append(
            f"""
            <tr>
              <td><b>{_esc(task.get("name") or task["id"])}</b><br /><small>{_esc(str(task.get("created_at", ""))[:19].replace("T", " "))}</small></td>
              <td>{stats["annotated_files"]}/{stats["total_files"]} 张</td>
              <td><span class="pill pill--pass">一致 {stats["agree"]}</span> <span class="pill pill--fail">不一致 {stats["disagree"]}</span></td>
              <td><a class="detail-link" href="/qa/onboarding-attributes?tab=annotate&task={_esc(task["id"])}">详情 →</a></td>
            </tr>"""
        )
    table = (
        f"""
        <table class="task-table">
          <thead><tr><th>任务</th><th>标注覆盖</th><th>与算法对比</th><th></th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""
        if rows
        else '<p class="sub">还没有标注任务。新建一个任务后，就可以逐张给照片标注肤色/脸型/身型。</p>'
    )
    return f"""
    <h1>数据标注</h1>
    <p class="sub">每个任务保存一轮标注结果，可与算法输出做一致率对比，用于评估算法改动。</p>
    <form class="new-task" method="post" action="/qa/annotations/tasks">
      <input name="name" placeholder="任务名，如：第一轮 · 光照边界" required maxlength="40" />
      <button type="submit">新建标注任务</button>
    </form>
    {table}"""


def _annotate_detail_content(entries: list[dict[str, Any]], overlays: dict[str, str], task: dict[str, Any], diff_only: bool) -> str:
    """任务详情：逐图标注网格，点选不落库，底部「保存标注」统一提交。"""
    stats = _annotation_stats(task, entries)
    base = f"/qa/onboarding-attributes?tab=annotate&task={_esc(task['id'])}"
    diff_link = base if diff_only else f"{base}&diff=1"
    diff_text = "← 查看全部" if diff_only else "一键对比（只看标注≠算法）"
    cards = [card for entry in entries if (card := _annotation_card(entry, task, overlays, diff_only))]
    cards_html = "".join(cards) or '<p class="sub">没有不一致的 case 🎉</p>'
    return f"""
    <h1>{_esc(task.get("name") or task["id"])}</h1>
    <p class="sub">点选只修改本地状态，点底部「保存标注」统一落库；标注与算法不一致的属性组会标红。</p>
    <div class="toolbar">
      <a class="pill" href="/qa/onboarding-attributes?tab=annotate">← 任务列表</a>
      <span class="pill">覆盖 {stats['annotated_files']}/{stats['total_files']} 张</span>
      <span class="pill pill--pass">一致 {stats['agree']}</span>
      <span class="pill pill--fail">不一致 {stats['disagree']}</span>
      <a class="pill" href="{diff_link}">{diff_text}</a>
      <a class="refresh" href="{base}{"&diff=1" if diff_only else ""}&refresh=1">更新分析</a>
    </div>
    <div class="grid grid--anno" data-task="{_esc(task['id'])}">{cards_html}</div>
    <div class="save-bar" id="saveBar" hidden>
      <span id="dirtyCount">有 0 项未保存修改</span>
      <button type="button" id="saveAnnotations">保存标注</button>
    </div>
    <script>
    (function () {{
      var grid = document.querySelector('.grid--anno');
      var saveBar = document.getElementById('saveBar');
      var dirtyCount = document.getElementById('dirtyCount');
      function groupValue(group) {{
        var sel = group.querySelector('.anno-opt.is-sel');
        return sel ? sel.dataset.value : '';
      }}
      function refreshDirty() {{
        var n = 0;
        grid.querySelectorAll('.anno-group').forEach(function (g) {{
          if (g.dataset.saved !== groupValue(g)) n += 1;
        }});
        dirtyCount.textContent = '有 ' + n + ' 项未保存修改';
        saveBar.hidden = n === 0;
      }}
      grid.querySelectorAll('.anno-opt').forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          var group = btn.closest('.anno-group');
          var wasSel = btn.classList.contains('is-sel');
          group.querySelectorAll('.anno-opt').forEach(function (b) {{ b.classList.remove('is-sel'); }});
          if (!wasSel) btn.classList.add('is-sel');
          refreshDirty();
        }});
      }});
      document.getElementById('saveAnnotations').addEventListener('click', async function () {{
        var annotations = {{}};
        grid.querySelectorAll('.anno-group').forEach(function (g) {{
          var value = groupValue(g);
          if (!value) return;
          var file = g.querySelector('.anno-opt').dataset.file;
          (annotations[file] = annotations[file] || {{}})[g.dataset.attrName] = value;
        }});
        var resp = await fetch('/qa/annotations/' + encodeURIComponent(grid.dataset.task) + '/batch', {{
          method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ annotations: annotations }})
        }});
        if (!resp.ok) {{ alert('保存失败，请重试'); return; }}
        location.reload();
      }});
    }})();
    </script>"""



# ---------------------------------------------------------------------------
# 标注叠加层：把算法的量测位置和数值直接画在照片上
# ---------------------------------------------------------------------------

_CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _pick_font(size: int) -> tuple[Any, bool]:
    for candidate in _CJK_FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size), True
            except Exception:
                continue
    return ImageFont.load_default(), False


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text_zh: str, text_en: str, font: Any, use_zh: bool, fill: tuple, outline: tuple = (0, 0, 0)) -> None:
    text = text_zh if use_zh else text_en
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        draw.text((xy[0] + dx, xy[1] + dy), text, font=font, fill=outline)
    draw.text(xy, text, font=font, fill=fill)


def _render_face_overlay(image: Image.Image, result: dict[str, Any]) -> Image.Image:
    canvas = image.convert("RGBA")
    tint = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    tint_draw = ImageDraw.Draw(tint)
    draw = ImageDraw.Draw(canvas)
    font, use_zh = _pick_font(max(18, canvas.size[1] // 42))

    geometry = debug_face_geometry(image) or {}
    region_names = {"forehead": "额", "left_cheek": "左颊", "right_cheek": "右颊", "jaw": "下颌"}
    for region in geometry.get("skin_regions", []):
        x0, y0, x1, y1 = region["box"]
        tint_draw.rectangle([x0, y0, x1, y1], fill=(46, 160, 67, 60))
        draw.rectangle([x0, y0, x1, y1], outline=(46, 160, 67), width=3)
        _draw_text(draw, (x0 + 4, y0 + 4), region_names.get(region["name"], region["name"]), region["name"], font, use_zh, (0, 120, 40))
    if geometry.get("bangs_band"):
        x0, y0, x1, y1 = geometry["bangs_band"]
        draw.rectangle([x0, y0, x1, y1], outline=(220, 38, 38), width=3)
        _draw_text(draw, (x0 + 4, max(0, y0 - font.size - 4)), "刘海检测带", "bangs band", font, use_zh, (220, 38, 38))
    colors = {"脸长": (147, 51, 234), "颧骨宽": (225, 29, 72), "额宽": (234, 138, 0), "下颌宽": (37, 99, 235)}
    for line in geometry.get("lines", []):
        color = colors.get(line["name"], (0, 0, 0))
        draw.line([tuple(line["from"]), tuple(line["to"])], fill=color, width=5)
        mx, my = (line["from"][0] + line["to"][0]) / 2, (line["from"][1] + line["to"][1]) / 2
        _draw_text(draw, (mx + 8, my - font.size / 2), f"{line['name']} {line['width']}", f"{line['name']} {line['width']}", font, use_zh, color)
    for name, (px, py) in geometry.get("points", {}).items():
        draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(255, 255, 255), outline=(25, 23, 25), width=2)
    canvas = Image.alpha_composite(canvas, tint)

    attrs = result.get("attributes", {})
    skin = attrs.get("skin_tone", {})
    shape = attrs.get("face_shape", {})
    skin_ev = skin.get("evidence") or {}
    shape_ev = shape.get("evidence") or {}
    r_value = (shape_ev.get("features") or {}).get("length_width_ratio")
    summary = f"肤色 {skin.get('label') or '—'} L*={skin_ev.get('l_star', '—')} ｜ 脸型 {shape.get('label') or '—'} r={r_value or '—'}"
    if shape.get("sub_label"):
        summary += f"（{shape['sub_label']}）"
    # alpha_composite 生成新图像对象，横幅必须在其后新建 Draw 再画。
    banner_draw = ImageDraw.Draw(canvas)
    banner_h = font.size + 18
    banner_draw.rectangle([0, 0, canvas.size[0], banner_h], fill=(25, 23, 25, 200))
    _draw_text(banner_draw, (10, 9), summary, summary, font, use_zh, (255, 255, 255), outline=(25, 23, 25))
    return canvas.convert("RGB")


def _render_body_overlay(image: Image.Image, result: dict[str, Any]) -> Image.Image:
    canvas = image.convert("RGBA")
    tint = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    tint_draw = ImageDraw.Draw(tint)
    draw = ImageDraw.Draw(canvas)
    font, use_zh = _pick_font(max(18, canvas.size[1] // 48))

    geometry = debug_body_geometry(image) or {}
    contour = geometry.get("contour") or []
    if contour:
        tint_draw.polygon([tuple(p) for p in contour], fill=(225, 29, 72, 40))
        draw.line([tuple(p) for p in contour] + [tuple(contour[0])], fill=(225, 29, 72), width=3)
    for arm in geometry.get("arms", []):
        draw.line([tuple(p) for p in arm], fill=(234, 179, 8), width=6)
        for px, py in arm:
            draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(234, 179, 8))
    band_ys = geometry.get("band_ys") or {}
    key_rows = [
        ("肩", band_ys.get("armpit_y"), (34, 197, 94)),
        ("腰", _best_row_y(geometry, band_ys, "waist", min), (59, 130, 246)),
        ("髋", _best_row_y(geometry, band_ys, "hip", max), (219, 39, 119)),
    ]
    for name, y, color in key_rows:
        if y is None:
            continue
        row = next((r for r in geometry.get("rows", []) if r["y"] == y), None)
        x0, x1 = (row["x0"], row["x1"]) if row and row["x0"] is not None else (0, canvas.size[0])
        draw.line([(x0, y), (x1, y)], fill=color, width=6)
        width_text = f"{row['width']}px" if row else ""
        reliable = "" if (row and row["reliable"]) else "（不可靠）" if use_zh else " (unreliable)"
        _draw_text(draw, (x1 + 8, y - font.size / 2), f"{name} {width_text}{reliable}", f"{name} {width_text}{reliable}", font, use_zh, color)
    for name, (px, py) in (geometry.get("points") or {}).items():
        draw.ellipse([px - 7, py - 7, px + 7, py + 7], fill=(255, 255, 255), outline=(25, 23, 25), width=2)
    canvas = Image.alpha_composite(canvas, tint)

    body = (result.get("attributes") or {}).get("body_shape", {})
    ratios = ((body.get("evidence") or {}).get("classification") or {}).get("ratios") or {}
    summary = f"身型 {body.get('label') or '—'} ｜ 髋/肩={ratios.get('hip_over_shoulder') or '—'} 腰/髋={ratios.get('waist_over_hip') or '—'}"
    # alpha_composite 生成新图像对象，横幅必须在其后新建 Draw 再画。
    banner_draw = ImageDraw.Draw(canvas)
    banner_h = font.size + 18
    banner_draw.rectangle([0, 0, canvas.size[0], banner_h], fill=(25, 23, 25, 200))
    _draw_text(banner_draw, (10, 9), summary, summary, font, use_zh, (255, 255, 255), outline=(25, 23, 25))
    return canvas.convert("RGB")


def _best_row_y(geometry: dict[str, Any], band_ys: dict[str, Any], band: str, pick: Any) -> int | None:
    rows = geometry.get("rows") or []
    if band == "waist":
        lo, hi = band_ys.get("waist_top", 0), band_ys.get("waist_bottom", 0)
    else:
        lo, hi = band_ys.get("hip_top", 0), band_ys.get("hip_bottom", 0)
    band_rows = [r for r in rows if lo <= r["y"] <= hi and r["width"] > 0]
    if not band_rows:
        return None
    reliable = [r for r in band_rows if r["reliable"]] or band_rows
    return pick(reliable, key=lambda r: r["width"])["y"]


def _overlay_name(file: str) -> str:
    return f"{OVERLAY_VERSION}__{file.replace('/', '__')}"


def _ensure_overlays(entries: list[dict[str, Any]], refresh: bool = False) -> dict[str, str]:
    """为每个条目生成（或复用）标注叠加图，返回 file → 相对 /qa-photos 的路径。"""
    QA_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    overlays: dict[str, str] = {}
    for entry in entries:
        item = entry["item"]
        source = QA_PHOTO_DIR / item["file"]
        target = QA_OVERLAY_DIR / _overlay_name(item["file"])
        if not refresh and target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            overlays[item["file"]] = f"_overlays/{target.name}"
            continue
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                if item["kind"] == "face":
                    overlay = _render_face_overlay(image, entry["result"])
                else:
                    overlay = _render_body_overlay(image, entry["result"])
            overlay.save(target, "JPEG", quality=88)
            overlays[item["file"]] = f"_overlays/{target.name}"
        except Exception:
            continue
    return overlays



def _metric_rows(attributes: dict[str, Any]) -> str:
    rows: list[str] = []
    skin = attributes.get("skin_tone") or {}
    skin_ev = skin.get("evidence") or {}
    if skin_ev.get("l_star") is not None:
        rows.append(("肤色 L* / ITA", f"{skin_ev['l_star']} / {skin_ev.get('ita_deg')}°"))
    face = attributes.get("face_shape") or {}
    face_ev = face.get("evidence") or {}
    features = face_ev.get("features") or {}
    if features:
        rows.append(("长宽比", str(features.get("length_width_ratio"))))
        rows.append(("下颌/颧骨", str(features.get("jaw_cheek_ratio"))))
        rows.append(("额/颧骨", str(features.get("forehead_cheek_ratio"))))
    body = attributes.get("body_shape") or {}
    body_ev = body.get("evidence") or {}
    measurements = body_ev.get("measurements") or {}
    ratios = (body_ev.get("classification") or {}).get("ratios") or {}
    if measurements:
        rows.append(("肩/髋/腰", f"{measurements.get('shoulder_width')} / {measurements.get('hip_width')} / {measurements.get('waist_width', '—')}"))
    if ratios:
        rows.append(("髋/肩 腰/髋", f"{ratios.get('hip_over_shoulder')} / {ratios.get('waist_over_hip')}"))
    return "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in rows)


def _attribute_chips(attributes: dict[str, Any]) -> str:
    chips = []
    for name, attr in attributes.items():
        label = attr.get("label") or "—"
        confidence = attr.get("confidence", 0.0)
        status = attr.get("status", "unknown")
        chips.append(
            f'<div class="attr attr--{_esc(status)}">'
            f'<span class="attr-name">{_esc(ATTRIBUTE_LABELS.get(name, name))}</span>'
            f'<b>{_esc(label)}</b>'
            f'<span class="attr-meta">{STATUS_LABELS.get(status, status)} · {int(round(confidence * 100))}%</span>'
            f"</div>"
        )
    return "".join(chips)


def _issue_list(result: dict[str, Any]) -> str:
    items = [f"<li><code>{_esc(issue['code'])}</code> {_esc(issue['message'])}</li>" for issue in result.get("issues", [])]
    return f'<ul class="issues">{"".join(items)}</ul>' if items else ""


def _card(entry: dict[str, Any], overlays: dict[str, str]) -> str:
    item, result = entry["item"], entry["result"]
    status = result.get("status", "unknown")
    candidates_html = ""
    face_attr = (result.get("attributes") or {}).get("face_shape") or {}
    candidates = face_attr.get("candidates") or []
    if len(candidates) > 1:
        candidates_html = '<div class="candidates">次选 ' + " / ".join(f"{_esc(c['label'])} {c['score']}" for c in candidates[1:]) + "</div>"
    overlay = overlays.get(item["file"])
    if overlay:
        thumb = f"""
        <label class="thumb thumb--toggle" title="点击切换：标注图 / 原图">
          <input type="checkbox" class="thumb-toggle" />
          <img class="thumb-overlay" loading="lazy" src="/qa-photos/{_esc(overlay)}" alt="{_esc(item['file'])} 标注图" />
          <img class="thumb-original" loading="lazy" src="/qa-photos/{_esc(item['file'])}" alt="{_esc(item['file'])} 原图" />
        </label>"""
    else:
        thumb = f'<div class="thumb"><img loading="lazy" src="/qa-photos/{_esc(item["file"])}" alt="{_esc(item["file"])}" /></div>'
    return f"""
    <article class="card card--{_esc(status)}">
      {thumb}
      <div class="card-body">
        <div class="card-head"><b>{_esc(item['file'])}</b><span class="status status--{_esc(status)}">{STATUS_LABELS.get(status, status)}</span></div>
        <div class="attrs">{_attribute_chips(result.get("attributes") or {})}</div>
        {candidates_html}
        <table class="metrics">{_metric_rows(result.get("attributes") or {})}</table>
        {_issue_list(result)}
        <div class="source"><a href="{_esc(item.get('source_url', '#'))}" target="_blank" rel="noreferrer">来源</a> · {_esc((item.get('alt') or '')[:60])}</div>
      </div>
    </article>
    """


def _summary(entries: list[dict[str, Any]]) -> str:
    counts: dict[str, dict[str, int]] = {}
    status_counts: dict[str, int] = {}
    for entry in entries:
        result = entry["result"]
        status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1
        for name, attr in (result.get("attributes") or {}).items():
            label = attr.get("label") or "未识别"
            counts.setdefault(name, {})[label] = counts.setdefault(name, {}).get(label, 0) + 1
    parts = [f'<span class="pill">{_esc(ATTRIBUTE_LABELS.get(name, name))}：' + " / ".join(f"{_esc(k)}×{v}" for k, v in sorted(v.items(), key=lambda kv: -kv[1])) + "</span>" for name, v in counts.items()]
    status_html = " ".join(f'<span class="pill pill--{_esc(k)}">{STATUS_LABELS.get(k, k)}×{v}</span>' for k, v in sorted(status_counts.items()))
    return status_html + "".join(parts)


# ---------------------------------------------------------------------------
# 数据分布：各属性标签的数量/占比 + 紧缺提示 + 上传扩充
# ---------------------------------------------------------------------------

def _all_annotations_union() -> dict[str, dict[str, str]]:
    """合并全部任务的标注（同一文件同一属性以较新的任务为准）。"""
    union: dict[str, dict[str, str]] = {}
    for task in _load_annotations().get("tasks", []):
        for file, attrs in (task.get("annotations") or {}).items():
            union.setdefault(file, {}).update(attrs)
    return union


def _distribution_section(entries: list[dict[str, Any]], annotated: dict[str, dict[str, str]], attr_name: str, attr_label: str, labels: list[str], kind: str) -> str:
    kind_entries = [e for e in entries if e["item"]["kind"] == kind]
    total = len(kind_entries)
    algo_counts = {label: 0 for label in labels}
    unidentified = 0
    for entry in kind_entries:
        label = ((entry["result"].get("attributes") or {}).get(attr_name) or {}).get("label")
        if label in algo_counts:
            algo_counts[label] += 1
        else:
            unidentified += 1
    anno_counts = {label: 0 for label in labels}
    for entry in kind_entries:
        value = (annotated.get(entry["item"]["file"]) or {}).get(attr_name)
        if value in anno_counts:
            anno_counts[value] += 1
    anno_total = sum(anno_counts.values())

    max_count = max([*algo_counts.values(), 1])
    scarce = min(labels, key=lambda label: algo_counts[label]) if total else None
    rows = []
    for label in labels:
        algo_n = algo_counts[label]
        anno_n = anno_counts[label]
        pct = round(algo_n / total * 100) if total else 0
        scarce_badge = '<span class="scarce">最紧缺</span>' if label == scarce and total else ""
        rows.append(
            f"""
            <tr>
              <td class="dist-label">{_esc(label)}{scarce_badge}</td>
              <td class="dist-bar-cell"><div class="dist-bar dist-bar--algo" style="width:{max(2, round(algo_n / max_count * 100))}%"></div></td>
              <td class="dist-num">{algo_n}（{pct}%）</td>
              <td class="dist-num dist-num--anno">{anno_n}</td>
            </tr>"""
        )
    if unidentified:
        pct = round(unidentified / total * 100) if total else 0
        rows.append(
            f"""
            <tr>
              <td class="dist-label dist-label--unknown">未识别</td>
              <td class="dist-bar-cell"><div class="dist-bar dist-bar--unknown" style="width:{max(2, round(unidentified / max_count * 100))}%"></div></td>
              <td class="dist-num">{unidentified}（{pct}%）</td>
              <td class="dist-num dist-num--anno">—</td>
            </tr>"""
        )
    return f"""
    <section class="dist-section">
      <h2>{_esc(attr_label)}<small>（{_esc("大头照" if kind == "face" else "全身照")}，共 {total} 张）</small></h2>
      <table class="dist-table">
        <thead><tr><th>标签</th><th>分布</th><th>算法预测</th><th>人工确认</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      <p class="dist-note">人工确认 {anno_total} 条（合并所有标注任务）。</p>
    </section>"""


def _dataset_content(entries: list[dict[str, Any]], uploaded: str, upload_error: str, upload_dup: str) -> str:
    annotated = _all_annotations_union()
    notice = ""
    if uploaded:
        notice = f'<p class="upload-notice upload-notice--ok">已上传 { _esc(uploaded) }，算法已自动识别，可在「实验结果」查看。</p>'
    elif upload_error:
        notice = f'<p class="upload-notice upload-notice--err">上传失败：{_esc(upload_error)}</p>'
    elif upload_dup:
        notice = f'<p class="upload-notice">这张照片之前传过了（{_esc(upload_dup)}），已跳过。</p>'
    sections = "".join(
        [
            _distribution_section(entries, annotated, "skin_tone", "肤色", SKIN_TONE_LABELS, "face"),
            _distribution_section(entries, annotated, "face_shape", "脸型", FACE_SHAPE_LABELS, "face"),
            _distribution_section(entries, annotated, "body_shape", "身型", BODY_SHAPE_LABELS, "body"),
        ]
    )
    return f"""
    <h1>数据分布</h1>
    <p class="sub">看哪类数据最紧缺，定向补图。标红「最紧缺」的类别优先找；上传后算法会自动识别并入分布。</p>
    <form class="upload-card" method="post" action="/qa/photos/upload" enctype="multipart/form-data">
      <b>上传照片扩充数据集</b>
      <div class="upload-row">
        <select name="kind"><option value="face">大头照</option><option value="body">全身照</option></select>
        <input type="file" name="image" accept="image/jpeg,image/png,image/webp" required />
        <button type="submit">上传</button>
      </div>
      <small>要求：大头照正脸清晰、露出额头；全身照正面站立、头顶到脚踝完整入镜。JPG/PNG/WebP，≤12MB。</small>
    </form>
    {notice}
    {sections}"""


def _results_content(entries: list[dict[str, Any]], overlays: dict[str, str]) -> str:
    face_entries = [e for e in entries if e["item"]["kind"] == "face"]
    body_entries = [e for e in entries if e["item"]["kind"] == "body"]
    return f"""
    <h1>实验结果</h1>
    <p class="sub">共 {len(entries)} 张（大头照 {len(face_entries)} / 全身照 {len(body_entries)}）。分析结果缓存在 qa_photos/_results.json，改图后点「重新分析」。卡片默认显示标注图，点击图片切换原图。</p>
    <div class="toolbar">{_summary(entries)}<a class="refresh" href="/qa/onboarding-attributes?tab=results&refresh=1">重新分析</a></div>
    <h2>大头照（肤色 / 脸型）</h2>
    <div class="grid">{"".join(_card(e, overlays) for e in face_entries)}</div>
    <h2>全身照（身型）</h2>
    <div class="grid">{"".join(_card(e, overlays) for e in body_entries)}</div>"""


def render_qa_page(content: str, active_tab: str) -> str:
    def tab(key: str, label: str) -> str:
        return f'<a class="tab{" is-active" if active_tab == key else ""}" href="/qa/onboarding-attributes?tab={key}">{label}</a>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>onboarding 属性识别 QA</title>
  <link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png" />
  <style>
    body {{ margin: 0; background: #f7f3ef; color: #191719; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif; }}
    .layout {{ display: flex; min-height: 100vh; }}
    .sidebar {{ width: 172px; flex-shrink: 0; background: #fff; border-right: 1px solid #e7ded9; padding: 24px 14px; position: sticky; top: 0; height: 100vh; box-sizing: border-box; }}
    .sidebar .logo {{ font-weight: 900; font-size: 15px; margin-bottom: 18px; }}
    .tab {{ display: block; padding: 10px 12px; border-radius: 12px; color: #4c4441; text-decoration: none; font-size: 14px; font-weight: 700; margin-bottom: 6px; }}
    .tab.is-active {{ background: #ffe4ee; color: #9b344b; }}
    main {{ flex: 1; min-width: 0; padding: 28px 26px 48px; }}
    h1 {{ font-size: 24px; margin: 0 0 4px; }}
    h2 {{ font-size: 19px; margin: 26px 0 12px; }}
    .sub {{ color: #6c6260; font-size: 13px; margin: 0 0 14px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0 16px; }}
    .pill {{ background: #fff; border: 1px solid #e7ded9; border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 700; }}
    .pill--pass {{ background: #e7f5ea; border-color: #cde7d4; }}
    .pill--warn {{ background: #fff4d8; border-color: #f0d48c; }}
    .pill--fail {{ background: #fde8e8; border-color: #f3c2c2; }}
    .refresh {{ margin-left: auto; background: #191719; color: #fff; border-radius: 999px; padding: 8px 14px; font-size: 12px; font-weight: 800; text-decoration: none; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
    .grid--anno {{ grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }}
    .card {{ background: #fff; border: 1px solid #e7ded9; border-radius: 16px; overflow: hidden; display: flex; flex-direction: column; }}
    .card--fail {{ border-color: #f3c2c2; }}
    .card--warn {{ border-color: #f0d48c; }}
    .card--diff {{ border-color: #f3c2c2; box-shadow: 0 0 0 2px rgba(220, 38, 38, .18); }}
    .thumb {{ aspect-ratio: 3 / 4; background: #efe9e4; overflow: hidden; display: block; cursor: pointer; position: relative; }}
    .thumb img {{ width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }}
    .thumb-toggle {{ display: none; }}
    .thumb-original {{ display: none !important; }}
    .thumb-toggle:checked ~ .thumb-original {{ display: block !important; }}
    .thumb-toggle:checked ~ .thumb-overlay {{ display: none !important; }}
    .thumb--toggle::after {{ content: "点图切换原图"; position: absolute; right: 8px; bottom: 8px; background: rgba(25,23,25,.72); color: #fff; font-size: 11px; border-radius: 999px; padding: 3px 9px; }}
    .anno-card .thumb {{ aspect-ratio: 4 / 5; cursor: default; }}
    .card-body {{ padding: 12px 14px 14px; }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; font-size: 13px; }}
    .status {{ border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 800; }}
    .status--pass {{ background: #e7f5ea; color: #166534; }}
    .status--warn {{ background: #fff4d8; color: #8a5a00; }}
    .status--fail {{ background: #fde8e8; color: #b91c1c; }}
    .attrs {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 4px; }}
    .attr {{ border: 1px solid #eee6e1; border-radius: 12px; padding: 6px 10px; display: flex; flex-direction: column; min-width: 76px; }}
    .attr--fail {{ border-color: #f3c2c2; background: #fffafa; }}
    .attr--warn {{ border-color: #f0d48c; background: #fffdf6; }}
    .attr-name {{ font-size: 11px; color: #8a807d; font-weight: 700; }}
    .attr b {{ font-size: 15px; margin: 2px 0; }}
    .attr-meta {{ font-size: 11px; color: #8a807d; }}
    .candidates {{ font-size: 11px; color: #8a807d; margin: 2px 0 6px; }}
    .metrics {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }}
    .metrics td {{ border-top: 1px solid #f3ede8; padding: 4px 0; color: #4c4441; }}
    .metrics td:first-child {{ color: #8a807d; width: 40%; }}
    .issues {{ margin: 8px 0 0; padding-left: 16px; font-size: 12px; color: #8a5a00; }}
    .issues code {{ background: #f7f3ef; border-radius: 6px; padding: 1px 5px; font-size: 11px; }}
    .source {{ margin-top: 8px; font-size: 11px; color: #b0a6a2; }}
    .source a {{ color: #9b344b; }}
    .new-task input, .task-switch select {{ border: 1px solid #e7ded9; border-radius: 10px; padding: 8px 10px; font-size: 13px; background: #fff; }}
    .new-task button {{ background: #191719; color: #fff; border: 0; border-radius: 10px; padding: 8px 14px; font-size: 13px; font-weight: 800; cursor: pointer; }}
    .new-task, .task-switch {{ display: inline-flex; gap: 8px; margin: 0; }}
    .anno-group {{ border-top: 1px solid #f3ede8; padding: 8px 0 4px; }}
    .anno-group-head {{ display: flex; justify-content: space-between; font-size: 12px; font-weight: 800; margin-bottom: 6px; }}
    .anno-group-head small {{ color: #8a807d; font-weight: 600; }}
    .anno-group.is-diff .anno-group-head span {{ color: #b91c1c; }}
    .anno-options {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .anno-opt {{ border: 1px solid #e7ded9; background: #fff; border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 700; cursor: pointer; color: #4c4441; }}
    .anno-opt:hover {{ border-color: #ff4f86; color: #ff4f86; }}
    .anno-opt.is-sel {{ background: #ff4f86; border-color: #ff4f86; color: #fff; }}
    .diff-badge {{ display: inline-block; margin-top: 6px; font-size: 11px; color: #b91c1c; background: #fde8e8; border-radius: 8px; padding: 3px 8px; }}
    .task-table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e7ded9; border-radius: 16px; overflow: hidden; margin-top: 16px; }}
    .task-table th, .task-table td {{ text-align: left; padding: 12px 16px; border-top: 1px solid #f3ede8; font-size: 13px; }}
    .task-table th {{ border-top: 0; background: #faf6f3; font-size: 12px; color: #8a807d; }}
    .task-table small {{ color: #8a807d; }}
    .detail-link {{ color: #ff4f86; font-weight: 800; text-decoration: none; }}
    .save-bar {{ position: fixed; left: 50%; transform: translateX(-50%); bottom: 22px; z-index: 30; display: flex; gap: 14px; align-items: center; background: #191719; color: #fff; border-radius: 999px; padding: 10px 18px; box-shadow: 0 14px 34px rgba(25,23,25,.28); font-size: 13px; }}
    .save-bar button {{ background: #ff4f86; color: #fff; border: 0; border-radius: 999px; padding: 9px 20px; font-size: 13px; font-weight: 800; cursor: pointer; }}
    a.pill {{ text-decoration: none; color: inherit; }}
    .upload-card {{ background: #fff; border: 1px dashed #f0b9cd; border-radius: 16px; padding: 16px 18px; margin: 10px 0 20px; }}
    .upload-card b {{ font-size: 14px; }}
    .upload-row {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 10px 0 8px; }}
    .upload-row select, .upload-row input {{ border: 1px solid #e7ded9; border-radius: 10px; padding: 8px 10px; font-size: 13px; background: #fff; }}
    .upload-row button {{ background: #ff4f86; color: #fff; border: 0; border-radius: 999px; padding: 9px 22px; font-size: 13px; font-weight: 800; cursor: pointer; }}
    .upload-card small {{ color: #8a807d; }}
    .upload-notice {{ border-radius: 12px; padding: 10px 14px; font-size: 13px; background: #fff4d8; }}
    .upload-notice--ok {{ background: #e7f5ea; }}
    .upload-notice--err {{ background: #fde8e8; }}
    .dist-section {{ margin-bottom: 26px; }}
    .dist-section h2 small {{ color: #8a807d; font-weight: 600; }}
    .dist-table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e7ded9; border-radius: 16px; overflow: hidden; }}
    .dist-table th, .dist-table td {{ text-align: left; padding: 10px 14px; border-top: 1px solid #f3ede8; font-size: 13px; }}
    .dist-table th {{ border-top: 0; background: #faf6f3; font-size: 12px; color: #8a807d; }}
    .dist-label {{ width: 110px; font-weight: 800; }}
    .dist-label--unknown {{ color: #b0a6a2; }}
    .dist-bar-cell {{ width: 46%; }}
    .dist-bar {{ height: 14px; border-radius: 999px; }}
    .dist-bar--algo {{ background: #ff4f86; }}
    .dist-bar--unknown {{ background: #d8d0cc; }}
    .dist-num {{ width: 110px; color: #4c4441; }}
    .dist-num--anno {{ color: #166534; font-weight: 800; }}
    .scarce {{ margin-left: 6px; background: #fde8e8; color: #b91c1c; border-radius: 8px; padding: 2px 7px; font-size: 11px; }}
    .dist-note {{ color: #8a807d; font-size: 12px; margin: 8px 0 0; }}
    @media (max-width: 760px) {{ .layout {{ flex-direction: column; }} .sidebar {{ width: 100%; height: auto; position: static; display: flex; gap: 8px; align-items: center; }} .tab {{ margin-bottom: 0; }} }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">onboarding QA</div>
      <a class="tab" href="/admin" style="margin-bottom:14px">← 管理后台</a>
      {tab("results", "实验结果")}
      {tab("annotate", "数据标注")}
      {tab("dataset", "数据分布")}
    </aside>
    <main>{content}</main>
  </div>
</body>
</html>"""


def _require_admin_redirect(request: Request) -> RedirectResponse | None:
    """QA 页面鉴权：未登录跳管理后台。返回 None 表示已通过。"""

    token = admin_token_from_request(request)
    if not token:
        return RedirectResponse(url="/admin", status_code=307)
    try:
        resolve_admin_user(token)
    except Exception:
        return RedirectResponse(url="/admin", status_code=307)
    return None


@router.get("/qa/onboarding-attributes", response_class=HTMLResponse)
def qa_onboarding_attributes(
    request: Request,
    tab: str = "results",
    task: str | None = None,
    diff: int = 0,
    refresh: int = 0,
    uploaded: str = "",
    upload_error: str = "",
    upload_dup: str = "",
) -> Response:
    denied = _require_admin_redirect(request)
    if denied is not None:
        return denied
    entries = _analyze_all(refresh=bool(refresh))
    overlays = _ensure_overlays(entries, refresh=bool(refresh))
    if tab == "annotate":
        selected = _find_annotation_task(_load_annotations(), task) if task else None
        if selected is None:
            return render_qa_page(_annotate_list_content(entries), "annotate")
        return render_qa_page(_annotate_detail_content(entries, overlays, selected, bool(diff)), "annotate")
    if tab == "dataset":
        return render_qa_page(_dataset_content(entries, uploaded, upload_error, upload_dup), "dataset")
    return render_qa_page(_results_content(entries, overlays), "results")


@router.post("/qa/photos/upload")
async def qa_upload_photo(request: Request) -> Response:
    """同事上传照片扩充数据集：校验 → 去重 → 落盘 → 立即跑算法并入缓存。"""
    denied = _require_admin_redirect(request)
    if denied is not None:
        return denied
    base = "/qa/onboarding-attributes?tab=dataset"

    def back(query: str) -> RedirectResponse:
        return RedirectResponse(url=f"{base}{query}", status_code=303)

    form = await request.form()
    kind = str(form.get("kind") or "")
    upload = form.get("image")
    if kind not in {"face", "body"}:
        return back("&upload_error=照片类型不正确")
    if upload is None or not hasattr(upload, "read"):
        return back("&upload_error=请选择要上传的照片")
    raw = await upload.read()
    if not raw:
        return back("&upload_error=请选择要上传的照片")
    if len(raw) > UPLOAD_MAX_BYTES:
        return back("&upload_error=照片超过 12MB，请压缩后再传")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        return back("&upload_error=无法识别照片内容")
    image = image.convert("RGB")
    if min(image.size) < 300:
        return back("&upload_error=照片分辨率太低，请换更清晰的")

    digest = hashlib.sha256(raw).hexdigest()[:12]
    filename = f"upload_{kind}_{digest}.jpg"
    rel = f"{kind}/{filename}"
    manifest = _load_manifest()
    if any(item["file"] == rel for item in manifest):
        return back(f"&upload_dup={filename}")

    if max(image.size) > UPLOAD_MAX_SIDE:
        ratio = UPLOAD_MAX_SIDE / max(image.size)
        image = image.resize((round(image.width * ratio), round(image.height * ratio)))
    target = QA_PHOTO_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "JPEG", quality=88)

    manifest.append(
        {
            "file": rel,
            "kind": kind,
            "source_url": "",
            "author": "同事上传",
            "query": "手动上传",
            "alt": getattr(upload, "filename", "") or "",
            "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    _save_manifest(manifest)

    result = analyze_face_photo(image) if kind == "face" else analyze_body_photo(image)
    cache = _load_cache()
    cache[rel] = {"mtime": target.stat().st_mtime, "result": result}
    QA_RESULTS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return back(f"&uploaded={filename}")


@router.post("/qa/annotations/tasks")
async def qa_create_annotation_task(request: Request) -> Response:
    denied = _require_admin_redirect(request)
    if denied is not None:
        return denied
    form = await request.form()
    name = str(form.get("name") or "").strip() or "未命名任务"
    data = _load_annotations()
    task_id = f"ann_{len(data['tasks']) + 1:03d}_{secrets.token_urlsafe(4)}"
    data["tasks"].append(
        {
            "id": task_id,
            "name": name[:40],
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "annotations": {},
        }
    )
    _save_annotations(data)
    return RedirectResponse(url=f"/qa/onboarding-attributes?tab=annotate&task={task_id}", status_code=303)


@router.post("/qa/annotations/{task_id}/batch")
async def qa_set_annotations_batch(task_id: str, request: Request) -> Response:
    """整体替换任务的标注集（页面网格的全量状态）。任一值非法则全部不落库。"""
    denied = _require_admin_redirect(request)
    if denied is not None:
        return denied
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    raw_annotations = payload.get("annotations")
    if not isinstance(raw_annotations, dict):
        return JSONResponse({"ok": False, "error": "invalid_annotations"}, status_code=422)

    manifest_files = {item["file"] for item in _load_manifest()}
    cleaned: dict[str, dict[str, str]] = {}
    for file, attrs in raw_annotations.items():
        if file not in manifest_files:
            return JSONResponse({"ok": False, "error": "unknown_file", "file": file}, status_code=404)
        if not isinstance(attrs, dict):
            return JSONResponse({"ok": False, "error": "invalid_attrs", "file": file}, status_code=422)
        kind = file.split("/", 1)[0]
        allowed = {name: set(labels) for name, _, labels in ANNOTATION_SCHEMA.get(kind, [])}
        for attr, value in attrs.items():
            if attr not in allowed:
                return JSONResponse({"ok": False, "error": "unknown_attr", "attr": attr}, status_code=422)
            if value not in allowed[attr]:
                return JSONResponse({"ok": False, "error": "invalid_value", "value": value}, status_code=422)
        if attrs:
            cleaned[file] = {str(attr): str(value) for attr, value in attrs.items()}

    data = _load_annotations()
    task = _find_annotation_task(data, task_id)
    if task is None:
        return JSONResponse({"ok": False, "error": "unknown_task"}, status_code=404)
    task["annotations"] = cleaned
    _save_annotations(data)
    return JSONResponse({"ok": True, "stats": _annotation_stats(task, _analyze_all())})

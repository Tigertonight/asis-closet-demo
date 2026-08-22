"""onboarding 属性识别算法的 QA 目检页面。

路由：`GET /qa/onboarding-attributes`（内部 QA 用，不对 C 端暴露）。
素材：`qa_photos/{face,body}/*.jpg` + `manifest.json`（来源溯源，见
scripts/collect_onboarding_qa_photos.py）。

分析结果按「文件 + mtime」缓存到 `qa_photos/_results.json`；
`?refresh=1` 强制全量重算。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from PIL import Image

from app.attribute_pipeline import analyze_body_photo, analyze_face_photo
from app.storage import ROOT_DIR

QA_PHOTO_DIR = ROOT_DIR / "qa_photos"
QA_RESULTS_CACHE = QA_PHOTO_DIR / "_results.json"

router = APIRouter(tags=["qa-onboarding"])

ATTRIBUTE_LABELS = {"skin_tone": "肤色", "face_shape": "脸型", "body_shape": "身型"}
STATUS_LABELS = {"pass": "通过", "warn": "存疑", "fail": "拒绝", "unknown": "未识别"}


def _load_manifest() -> list[dict[str, Any]]:
    path = QA_PHOTO_DIR / "manifest.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


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


def _card(entry: dict[str, Any]) -> str:
    item, result = entry["item"], entry["result"]
    status = result.get("status", "unknown")
    candidates_html = ""
    face_attr = (result.get("attributes") or {}).get("face_shape") or {}
    candidates = face_attr.get("candidates") or []
    if len(candidates) > 1:
        candidates_html = '<div class="candidates">次选 ' + " / ".join(f"{_esc(c['label'])} {c['score']}" for c in candidates[1:]) + "</div>"
    return f"""
    <article class="card card--{_esc(status)}">
      <div class="thumb"><img loading="lazy" src="/qa-photos/{_esc(item['file'])}" alt="{_esc(item['file'])}" /></div>
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


def render_qa_page(entries: list[dict[str, Any]]) -> str:
    face_entries = [e for e in entries if e["item"]["kind"] == "face"]
    body_entries = [e for e in entries if e["item"]["kind"] == "body"]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>onboarding 属性识别 QA</title>
  <style>
    body {{ margin: 0; background: #f7f3ef; color: #191719; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif; }}
    main {{ width: min(1280px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }}
    h1 {{ font-size: 26px; margin: 8px 0 4px; }}
    h2 {{ font-size: 19px; margin: 26px 0 12px; }}
    .sub {{ color: #6c6260; font-size: 13px; margin: 0 0 14px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0 4px; }}
    .pill {{ background: #fff; border: 1px solid #e7ded9; border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 700; }}
    .pill--pass {{ background: #e7f5ea; border-color: #cde7d4; }}
    .pill--warn {{ background: #fff4d8; border-color: #f0d48c; }}
    .pill--fail {{ background: #fde8e8; border-color: #f3c2c2; }}
    .refresh {{ margin-left: auto; background: #191719; color: #fff; border-radius: 999px; padding: 8px 14px; font-size: 12px; font-weight: 800; text-decoration: none; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
    .card {{ background: #fff; border: 1px solid #e7ded9; border-radius: 16px; overflow: hidden; display: flex; flex-direction: column; }}
    .card--fail {{ border-color: #f3c2c2; }}
    .card--warn {{ border-color: #f0d48c; }}
    .thumb {{ aspect-ratio: 3 / 4; background: #efe9e4; overflow: hidden; }}
    .thumb img {{ width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }}
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
  </style>
</head>
<body>
  <main>
    <h1>onboarding 属性识别 QA</h1>
    <p class="sub">共 {len(entries)} 张（大头照 {len(face_entries)} / 全身照 {len(body_entries)}）。分析结果缓存在 qa_photos/_results.json，改图后点「重新分析」。</p>
    <div class="toolbar">{_summary(entries)}<a class="refresh" href="/qa/onboarding-attributes?refresh=1">重新分析</a></div>
    <h2>大头照（肤色 / 脸型）</h2>
    <div class="grid">{"".join(_card(e) for e in face_entries)}</div>
    <h2>全身照（身型）</h2>
    <div class="grid">{"".join(_card(e) for e in body_entries)}</div>
  </main>
</body>
</html>"""


@router.get("/qa/onboarding-attributes", response_class=HTMLResponse)
def qa_onboarding_attributes(refresh: int = 0) -> str:
    return render_qa_page(_analyze_all(refresh=bool(refresh)))

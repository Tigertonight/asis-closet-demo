from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analyzer import ROOT_DIR, analyze_fixture_case, self_test_results


RESULTS_DIR = ROOT_DIR / "tests" / "results"
SELF_TEST_RESULTS = RESULTS_DIR / "self_test_results.json"
SELF_TEST_REPORT = RESULTS_DIR / "self_test_report.html"
CONTACT_SHEET = RESULTS_DIR / "contact_sheet.jpg"
REGION_OVERLAY_SHEET = RESULTS_DIR / "region_overlay_sheet.jpg"
REGION_OVERLAY_DIR = RESULTS_DIR / "overlays"


def main() -> None:
    result = generate_qa_artifacts()
    for path in result["paths"].values():
        print(f"wrote {path}")


def generate_qa_artifacts() -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REGION_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    results = self_test_results()
    SELF_TEST_RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_contact_sheet(results)
    write_region_overlay_sheet(results)
    write_report(results)
    return {
        "status": "ok",
        "total": results.get("total", 0),
        "passed": results.get("passed", 0),
        "failed": results.get("failed", 0),
        "seasonal_accuracy": results.get("product_metrics", {}).get("seasonal_accuracy", {}),
        "paths": {
            "self_test_results": str(SELF_TEST_RESULTS),
            "contact_sheet": str(CONTACT_SHEET),
            "region_overlay_sheet": str(REGION_OVERLAY_SHEET),
            "region_overlay_dir": str(REGION_OVERLAY_DIR),
            "self_test_report": str(SELF_TEST_REPORT),
        },
        "urls": {
            "contact_sheet": "/qa-artifacts/contact_sheet.jpg",
            "region_overlay_sheet": "/qa-artifacts/region_overlay_sheet.jpg",
            "region_overlay_dir": "/qa-artifacts/overlays",
            "self_test_report": "/qa-artifacts/self_test_report.html",
        },
    }


def write_contact_sheet(results: dict) -> None:
    cases = results.get("cases", [])
    columns = 6
    thumb_w, thumb_h = 170, 170
    label_h = 74
    gap = 14
    margin = 24
    header_h = 112
    rows = (len(cases) + columns - 1) // columns
    width = margin * 2 + columns * thumb_w + (columns - 1) * gap
    height = header_h + margin + rows * (thumb_h + label_h + gap)
    sheet = Image.new("RGB", (width, height), (249, 246, 244))
    draw = ImageDraw.Draw(sheet)
    title_font = _font(30)
    body_font = _font(16)
    small_font = _font(13)

    acc = results.get("product_metrics", {}).get("seasonal_accuracy", {})
    title = f"AI 色彩测试 MVP QA · {results.get('passed', 0)}/{results.get('total', 0)} 通过"
    subtitle = f"季节型 Top-1 {acc.get('top1_rate', 0) * 100:.1f}% · Top-2 {acc.get('top2_rate', 0) * 100:.1f}%"
    draw.text((margin, 24), title, fill=(28, 27, 32), font=title_font)
    draw.text((margin, 66), subtitle, fill=(124, 85, 98), font=body_font)

    for index, case in enumerate(cases):
        row, col = divmod(index, columns)
        x = margin + col * (thumb_w + gap)
        y = header_h + row * (thumb_h + label_h + gap)
        image_path = ROOT_DIR / case.get("image", "")
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            image = Image.new("RGB", (thumb_w, thumb_h), (230, 224, 224))
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (thumb_w, thumb_h), (255, 255, 255))
        frame.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        sheet.paste(frame, (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(232, 222, 224), width=1)

        capture = case.get("result_summary", {}).get("capture", {})
        tier = capture.get("result_tier_label") or case.get("actual_status", "")
        status_color = (28, 117, 72) if case.get("passed") else (178, 38, 30)
        draw.text((x, y + thumb_h + 8), _clip(case.get("name", ""), 12), fill=(28, 27, 32), font=body_font)
        draw.text((x, y + thumb_h + 32), _clip(str(tier), 14), fill=status_color, font=small_font)
        draw.text((x, y + thumb_h + 52), _clip(case.get("id", ""), 18), fill=(125, 121, 125), font=small_font)

    sheet.save(CONTACT_SHEET, quality=92)


def write_region_overlay_sheet(results: dict) -> None:
    REGION_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    cases = [case for case in results.get("cases", []) if case.get("actual_status") == "analyzed"]
    columns = 4
    thumb_w, thumb_h = 236, 276
    label_h = 82
    gap = 16
    margin = 24
    header_h = 126
    rows = (len(cases) + columns - 1) // columns
    width = margin * 2 + columns * thumb_w + (columns - 1) * gap
    height = header_h + margin + rows * (thumb_h + label_h + gap)
    sheet = Image.new("RGB", (width, height), (249, 246, 244))
    draw = ImageDraw.Draw(sheet)
    title_font = _font(30)
    body_font = _font(16)
    small_font = _font(13)
    draw.text((margin, 24), "AI 色彩测试采样区域 QA", fill=(28, 27, 32), font=title_font)
    draw.text((margin, 68), "蓝色=肤色区域 · 紫色=眼部/发际区域 · 黄色=色卡区域", fill=(124, 85, 98), font=body_font)

    for index, case in enumerate(cases):
        row, col = divmod(index, columns)
        x = margin + col * (thumb_w + gap)
        y = header_h + row * (thumb_h + label_h + gap)
        image_path = ROOT_DIR / case.get("image", "")
        skin_source = ""
        contrast_source = ""
        try:
            image = Image.open(image_path).convert("RGB")
            analysis = analyze_fixture_case(case["id"])
            skin_source = analysis.get("pipeline", {}).get("skin_tone", {}).get("evidence", {}).get("region_source", "")
            contrast_source = analysis.get("pipeline", {}).get("feature_contrast", {}).get("evidence", {}).get("region_source", "")
            overlay = _draw_analysis_overlay(image, analysis)
            _save_case_overlay(case["id"], overlay)
        except Exception:
            overlay = Image.new("RGB", (thumb_w, thumb_h), (230, 224, 224))

        overlay.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (thumb_w, thumb_h), (255, 255, 255))
        frame.paste(overlay, ((thumb_w - overlay.width) // 2, (thumb_h - overlay.height) // 2))
        sheet.paste(frame, (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(232, 222, 224), width=1)

        capture = case.get("result_summary", {}).get("capture", {})
        draw.text((x, y + thumb_h + 8), _clip(case.get("name", ""), 14), fill=(28, 27, 32), font=body_font)
        draw.text((x, y + thumb_h + 32), _clip(capture.get("result_tier_label") or case.get("actual_status", ""), 16), fill=(124, 85, 98), font=small_font)
        draw.text((x, y + thumb_h + 52), _clip(f"{skin_source or '-'} / {contrast_source or '-'}", 25), fill=(125, 121, 125), font=small_font)

    sheet.save(REGION_OVERLAY_SHEET, quality=92)


def _save_case_overlay(case_id: str, overlay: Image.Image) -> None:
    overlay_path = REGION_OVERLAY_DIR / f"{case_id}.jpg"
    overlay.convert("RGB").save(overlay_path, quality=92)


def _draw_analysis_overlay(image: Image.Image, analysis: dict) -> Image.Image:
    output = image.copy()
    draw = ImageDraw.Draw(output, "RGBA")
    width = max(2, round(max(output.size) / 360))

    face = analysis.get("pipeline", {}).get("face_cv", {}).get("evidence", {}).get("primary_face", {}).get("box")
    if face:
        _draw_box(draw, face, (255, 79, 134, 215), width + 1)

    card = analysis.get("pipeline", {}).get("color_card_cv", {}).get("evidence", {}).get("card_box")
    if card:
        _draw_box(draw, card, (242, 192, 80, 220), width + 1)

    skin_regions = analysis.get("pipeline", {}).get("skin_tone", {}).get("evidence", {}).get("regions", [])
    for region in skin_regions:
        _draw_box(draw, region.get("box", {}), (72, 124, 255, 220), width)

    feature_regions = analysis.get("pipeline", {}).get("feature_contrast", {}).get("evidence", {}).get("regions", {})
    for region in feature_regions.values():
        _draw_box(draw, region, (146, 86, 210, 220), width)

    keypoints = analysis.get("pipeline", {}).get("skin_tone", {}).get("evidence", {}).get("landmark_keypoints", {})
    radius = max(3, width + 1)
    for point in keypoints.values():
        px, py = int(point.get("x", 0)), int(point.get("y", 0))
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=(255, 255, 255, 210), outline=(255, 79, 134, 230), width=width)
    return output


def _draw_box(draw: ImageDraw.ImageDraw, box: dict, color: tuple[int, int, int, int], width: int) -> None:
    if not box:
        return
    x = int(box.get("x", 0))
    y = int(box.get("y", 0))
    w = int(box.get("width", 0))
    h = int(box.get("height", 0))
    if w <= 0 or h <= 0:
        return
    for offset in range(width):
        draw.rectangle((x - offset, y - offset, x + w + offset, y + h + offset), outline=color)
    fill = (color[0], color[1], color[2], 28)
    draw.rectangle((x, y, x + w, y + h), fill=fill)


def write_report(results: dict) -> None:
    seasonal = results.get("product_metrics", {}).get("seasonal_accuracy", {})
    gates = results.get("acceptance_gates", [])
    rows = []
    for case in results.get("cases", []):
        capture = case.get("result_summary", {}).get("capture", {})
        overlay_link = (
            f"<a href='/qa-artifacts/overlays/{esc(case.get('id'))}.jpg'>采样图</a>"
            if case.get("actual_status") == "analyzed"
            else "-"
        )
        rows.append(
            "<tr>"
            f"<td><b>{esc(case.get('name'))}</b><div class='small'>{esc(case.get('group'))} · {esc(case.get('id'))}</div></td>"
            f"<td>{esc(case.get('expected_status'))}<br>{esc(case.get('actual_status'))}</td>"
            f"<td>{esc(capture.get('result_tier_label') or capture.get('quality_label') or '-')}</td>"
            f"<td>{overlay_link}</td>"
            f"<td class='small'>{esc(', '.join(case.get('issues') or []) or '无')}</td>"
            f"<td class=\"{'ok' if case.get('passed') else 'fail'}\"><b>{'通过' if case.get('passed') else '需检查'}</b></td>"
            "</tr>"
        )

    gate_cards = "".join(
        f"<div class='gate {esc(gate.get('status'))}'><b>{esc(gate.get('label'))}</b>"
        f"<span>当前 {float(gate.get('rate', 0)) * 100:.1f}% · 目标 {esc(gate.get('target'))}</span>"
        f"<p>{esc(gate.get('message'))}</p></div>"
        for gate in gates
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AI 色彩测试 MVP 自测报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif; margin: 32px; background: #f7f4f2; color: #1c1b20; }}
    h1 {{ margin-bottom: 8px; }}
    .hero, .gate, table {{ background: #fff; border: 1px solid #eee3e6; border-radius: 12px; box-shadow: 0 12px 36px rgba(90, 56, 66, .06); }}
    .hero {{ padding: 20px 24px; margin-bottom: 18px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 18px 0; }}
    .gate {{ padding: 14px 16px; }}
    .gate.pass {{ border-color: #cfe8d8; }}
    .gate.warn {{ border-color: #efd99a; }}
    .gate span, .small {{ display: block; color: #766f73; font-size: 13px; line-height: 1.5; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #eee8ea; text-align: left; vertical-align: top; }}
    th {{ background: #fbf0f3; }}
    .ok {{ color: #137333; }}
    .fail {{ color: #b3261e; }}
  </style>
</head>
<body>
  <div class="hero">
    <h1>AI 色彩测试 MVP 自测报告</h1>
    <p><b>{results.get('passed', 0)}/{results.get('total', 0)}</b> 通过，季节型 Top-1 <b>{float(seasonal.get('top1_rate', 0)) * 100:.1f}%</b>，Top-2 <b>{float(seasonal.get('top2_rate', 0)) * 100:.1f}%</b></p>
  </div>
  <h2>验收门槛</h2>
  <div class="metrics">{gate_cards}</div>
  <h2>采样区域</h2>
  <p><a href="/qa-artifacts/region_overlay_sheet.jpg">查看关键点与采样区域叠加图</a></p>
  <h2>用例明细</h2>
  <table>
    <thead><tr><th>样本</th><th>期望/实际</th><th>用户结论</th><th>采样</th><th>问题码</th><th>结果</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    SELF_TEST_REPORT.write_text(html_text, encoding="utf-8")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


if __name__ == "__main__":
    main()

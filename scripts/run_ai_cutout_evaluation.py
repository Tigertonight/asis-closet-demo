"""Run five high-value garment cases through the real closet import API.

The script intentionally records the provider that actually produced each cutout.
It never labels a local fallback as an AI result.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "closet_cutout_imagegen" / "generated"
REPORT_ROOT = ROOT_DIR / "outputs" / "closet_ai_cutout_evaluation"
CASES = [
    ("D01", "D01_lace_blouse.png", "蕾丝边缘", "细节边缘与半透面料"),
    ("B01", "B01_model_wearing_white_shirt.png", "人物穿着", "人体、皮肤与白衬衫分离"),
    ("R01", "R01_shirt_on_wooden_floor_shadow.png", "复杂背景", "木地板与投影去除"),
    ("S01", "S01_two_similar_white_sneakers.png", "双鞋组合", "同类多主体与鞋带细节"),
    ("L01", "L01_xhs_style_note_cover_collage.png", "拼贴封面", "多图、文字与非单品场景的拒绝能力"),
]


def _login(client: httpx.Client) -> str:
    phone = f"+86139{datetime.now().strftime('%H%M%S%f')[-8:]}"
    started = client.post("/auth/phone/start", json={"phone": phone}).raise_for_status().json()
    verified = client.post("/auth/phone/verify", json={"phone": phone, "code": started["dev_code"]}).raise_for_status().json()
    return str(verified["access_token"])


def _path_label(item: dict[str, Any]) -> str:
    pipeline = item.get("pipeline") or {}
    ai_provider = str((pipeline.get("ai_cutout") or {}).get("provider") or "")
    if (pipeline.get("ai_cutout") or {}).get("status") == "ok" and ai_provider == "runway_google_generate_content":
        return "AI 抠图（复用试穿 Runway 服务）"
    if (pipeline.get("ai_cutout") or {}).get("status") == "ok":
        return "AI 抠图（Nano Banana）"
    segmentation = pipeline.get("segmentation") or {}
    if segmentation.get("provider") == "segformer_b2_clothes":
        return "本地语义分割兜底（SegFormer + rembg）"
    if segmentation.get("provider") == "top_fallback":
        return "原有检测器兜底"
    return "未生成可用单品"


def _assessment(item: dict[str, Any] | None, response: dict[str, Any]) -> str:
    if item is None:
        return "未入柜：系统未生成可确认的单品。"
    quality = item.get("quality") or {}
    if quality.get("status") == "usable":
        return "可用：可以进入下一轮人工目检。"
    if quality.get("status") == "review":
        return "待确认：轮廓或主体可能需要人工复核。"
    return f"未通过：{response.get('message') or '未达到入柜质量阈值。'}"


def _save_asset(client: httpx.Client, public_path: str | None, destination: Path) -> str | None:
    if not public_path:
        return None
    response = client.get(public_path)
    if response.status_code != 200:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return destination.name


def _report_html(results: list[dict[str, Any]], generated_at: str) -> str:
    ai_count = sum(1 for row in results if row["path"].startswith("AI 抠图"))
    fallback_count = sum(1 for row in results if "兜底" in row["path"])
    no_item_count = sum(1 for row in results if row["item"] is None)
    cards = []
    for row in results:
        item = row["item"] or {}
        quality = item.get("quality") or {}
        attempt = row.get("ai_attempt") or {}
        status = quality.get("status") or "no_item"
        source_image = f"inputs/{row['file']}"
        output_image = f"outputs/{row['output_file']}" if row.get("output_file") else ""
        output_caption = row.get("output_caption") or "接口实际输出"
        output_markup = f'<img src="{html.escape(output_image)}" alt="实际输出" />' if output_image else '<div class="empty">没有生成可展示的透明单品</div>'
        cards.append(
            f'''<article class="case-card status-{html.escape(status)}">
              <header><span class="case-id">{html.escape(row['id'])}</span><div><h2>{html.escape(row['name'])}</h2><p>{html.escape(row['challenge'])}</p></div></header>
              <div class="compare"><figure><figcaption>输入图</figcaption><img src="{html.escape(source_image)}" alt="{html.escape(row['name'])} 输入图" /></figure><figure><figcaption>{html.escape(output_caption)}</figcaption>{output_markup}</figure></div>
              <dl><div><dt>实际路径</dt><dd>{html.escape(row['path'])}</dd></div><div><dt>AI 调用</dt><dd>{html.escape(str(attempt.get('status') or '—'))} · {html.escape(str(attempt.get('reason') or attempt.get('provider') or '—'))}</dd></div><div><dt>质量判断</dt><dd>{html.escape(status)} · {html.escape(str(quality.get('score') or '—'))}</dd></div></dl>
              <p class="verdict">{html.escape(row['assessment'])}</p>
            </article>'''
        )
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>selfit · AI 抠图接口验收</title><style>
      :root{{--rose:#ff4f86;--ink:#292226;--muted:#7f7379;--line:#f0dfe5;--paper:#fffafa;--canvas:#f8f1f4}}*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--ink);font-family:"PingFang SC","Noto Sans CJK SC",sans-serif}}main{{width:min(1160px,calc(100% - 32px));margin:0 auto;padding:56px 0 84px}}.eyebrow{{font:600 12px/1.2 "Helvetica Neue",sans-serif;letter-spacing:.14em;color:#b75475;text-transform:uppercase}}h1{{font:400 clamp(44px,7vw,82px)/.9 Didot,"Bodoni 72",serif;letter-spacing:-.06em;margin:14px 0 12px}}.intro{{max-width:660px;color:var(--muted);font-size:16px;line-height:1.7}}.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:34px 0 28px}}.metric{{background:rgba(255,255,255,.8);border:1px solid var(--line);border-radius:18px;padding:18px 20px}}.metric b{{display:block;font:400 38px/.9 Didot,serif;color:var(--rose)}}.metric span{{color:var(--muted);font-size:13px}}.notice{{border-left:2px solid var(--rose);padding:12px 15px;background:rgba(255,255,255,.52);color:#62555b;line-height:1.65;margin-bottom:26px}}.cases{{display:grid;gap:18px}}.case-card{{background:#fff;border:1px solid var(--line);border-radius:24px;padding:22px;box-shadow:0 10px 32px rgba(78,41,57,.05)}}.case-card header{{display:flex;align-items:flex-start;gap:12px;margin-bottom:18px}}.case-id{{min-width:42px;padding:6px 7px;border-radius:999px;background:#fff0f5;color:#be4c73;text-align:center;font:600 12px/1.1 "Helvetica Neue",sans-serif}}h2{{margin:0;font-family:"Songti SC","STSong",serif;font-size:22px;font-weight:600}}header p{{margin:4px 0 0;color:var(--muted);font-size:13px}}.compare{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}figure{{margin:0;min-width:0;background:#fffafa;border-radius:16px;padding:10px;border:1px solid #f6e9ee}}figcaption{{font-size:12px;color:#8b777f;margin:1px 2px 9px}}figure img{{width:100%;height:300px;display:block;object-fit:contain;border-radius:10px;background:linear-gradient(45deg,#f8f5f6 25%,transparent 25%) 0 0/18px 18px,linear-gradient(-45deg,#f8f5f6 25%,transparent 25%) 0 0/18px 18px,#fff}}.compare figure:first-child img{{background:#f7f2f4}}.empty{{height:300px;display:grid;place-items:center;text-align:center;color:#9f8e95;font-size:14px;padding:28px}}dl{{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:12px;margin:16px 0 0}}dl div{{padding:11px 12px;background:#fffafa;border-radius:12px}}dt{{font-size:11px;color:#9a858d;margin-bottom:5px}}dd{{margin:0;font-size:13px;line-height:1.45}}.verdict{{margin:14px 0 0;font-size:14px;line-height:1.5}}.status-usable .verdict{{color:#43785e}}.status-review .verdict{{color:#a87538}}.status-no_item .verdict{{color:#9b556d}}footer{{margin-top:34px;color:#98868d;font-size:12px}}@media(max-width:700px){{main{{width:min(100% - 24px,560px);padding-top:34px}}.summary,.compare,dl{{grid-template-columns:1fr}}figure img,.empty{{height:250px}}}}
      </style></head><body><main><span class="eyebrow">selfit · backend validation</span><h1>AI 抠图接口验收</h1><p class="intro">5 张高价值测试素材通过 <code>/closet/import/upload</code> 的真实返回结果。此页仅显示实际走到的模型或兜底路径，不把失败结果包装为 AI 成功。</p><section class="summary"><div class="metric"><b>{ai_count}/5</b><span>实际走 AI 图像抠图</span></div><div class="metric"><b>{fallback_count}/5</b><span>落入本地兜底</span></div><div class="metric"><b>{no_item_count}/5</b><span>未产出可用单品</span></div></section><p class="notice">生成时间：{html.escape(generated_at)}。AI 路径只有在模型已配置并返回透明 PNG、且质量检查通过时才会显示为成功。</p><section class="cases">{''.join(cards)}</section><footer>报告由本地后端接口批量生成；输入与输出副本均保存在同一目录，便于离线审阅。</footer></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORT_ROOT / f"backend_ai_cutout_{timestamp}"
    (report_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (report_dir / "outputs").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    with httpx.Client(base_url=args.base_url, timeout=httpx.Timeout(240.0)) as client:
        token = _login(client)
        client.headers["Authorization"] = f"Bearer {token}"
        for case_id, filename, name, challenge in CASES:
            source_path = FIXTURE_DIR / filename
            shutil.copy2(source_path, report_dir / "inputs" / filename)
            with source_path.open("rb") as image_file:
                response = client.post("/closet/import/upload", files={"images": (filename, image_file, "image/png")})
            response.raise_for_status()
            payload = response.json()
            item = (payload.get("items") or [None])[0]
            attempts = (payload.get("summary") or {}).get("ai_attempts") or []
            attempt = attempts[0] if attempts else {}
            output_name = None
            output_caption = "接口实际输出"
            raw_output_path = attempt.get("raw_output_path")
            if raw_output_path:
                output_name = _save_asset(client, raw_output_path, report_dir / "outputs" / f"{case_id}-ai-raw.png")
                output_caption = "AI 原始输出（未通过透明度校验）"
            if item:
                if not raw_output_path:
                    output_name = _save_asset(client, (item.get("assets") or {}).get("cutout_path"), report_dir / "outputs" / f"{case_id}-cutout.png")
                if output_name and not raw_output_path:
                    output_caption = "实际入柜输出"
            results.append({
                "id": case_id,
                "file": filename,
                "name": name,
                "challenge": challenge,
                "item": item,
                "path": _path_label(item or {}),
                "assessment": _assessment(item, payload),
                "output_file": output_name,
                "output_caption": output_caption,
                "ai_attempt": attempt,
                "response": payload,
            })

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    (report_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "index.html").write_text(_report_html(results, generated_at), encoding="utf-8")
    print(report_dir / "index.html")


if __name__ == "__main__":
    main()

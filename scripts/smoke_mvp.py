from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "tests" / "results" / "smoke_mvp_results.json"
SMOKE_CASES = [
    ("season_spring_bright", "standard"),
    ("season_summer_light", "standard"),
    ("season_autumn_deep", "standard"),
    ("season_winter_clear", "standard"),
    ("real_social_screenshot_auto_crop", "light_note"),
    ("real_colorful_clothes_no_card", "light_note"),
    ("real_colorful_poster_no_card", "light_note"),
    ("real_warm_indoor_light_no_card", "low_confidence"),
    ("real_screen_cool_light_no_card", "low_confidence"),
    ("real_clear_glasses", "standard"),
    ("real_bangs_forehead", "light_note"),
    ("real_hand_near_face", "light_note"),
    ("card_missing", "light_note"),
    ("card_fake_grid", "low_confidence"),
    ("portrait_sunglasses", "retake"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke check the color diagnosis MVP service.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Service base URL, default http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=8.0, help="Request timeout in seconds")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Write smoke result JSON to this path")
    parser.add_argument("--no-write", action="store_true", help="Only print the result, do not write JSON")
    args = parser.parse_args()

    result = smoke_mvp(args.base_url.rstrip("/"), args.timeout)
    if not args.no_write:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["output"] = str(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "ok":
        raise SystemExit(1)


def smoke_mvp(base_url: str = DEFAULT_BASE_URL, timeout: float = 8.0) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    status_payload = _get_json(f"{base_url}/mvp/status", timeout)
    checks.extend(evaluate_status_payload(status_payload))

    for case_id, expected_tier in SMOKE_CASES:
        payload = _get_json(f"{base_url}/fixtures/{case_id}/analyze", timeout)
        checks.extend(evaluate_case_payload(case_id, expected_tier, payload))

    html = _get_text(f"{base_url}/mvp", timeout)
    checks.append(_check("/mvp 页面包含快速体验样本", "快速体验样本" in html))
    checks.append(_check("/mvp 页面包含产品 Demo 链接", "/demo?case=season_spring_bright" in html))
    demo_html = _get_text(f"{base_url}/demo", timeout)
    checks.extend(evaluate_demo_page(demo_html))

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "ok" if not failed else "failed",
        "base_url": base_url,
        "total": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }


def evaluate_status_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    summary = payload.get("summary", {})
    demo_cases = payload.get("demo_cases", [])
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    return [
        _check("MVP 状态 ready", payload.get("status") == "ready", payload.get("status")),
        _check(f"回归样本 {passed}/{total}", total > 0 and passed == total and summary.get("failed") == 0, summary),
        _check("标准样本数不少于 8", summary.get("standard_count", 0) >= 8, summary.get("standard_count")),
        _check("包含核心与真实上传演示样本", len(demo_cases) >= 12, [case.get("id") for case in demo_cases]),
        _check("交接文档入口存在", payload.get("artifact_urls", {}).get("handoff") == "/mvp/handoff", payload.get("artifact_urls", {})),
        _check("试用指南入口存在", payload.get("artifact_urls", {}).get("pilot_guide") == "/mvp/pilot-guide", payload.get("artifact_urls", {})),
    ]


def evaluate_demo_page(html: str) -> list[dict[str, Any]]:
    required_cases = [
        "season_spring_bright",
        "season_summer_light",
        "season_autumn_deep",
        "season_winter_clear",
        "card_missing",
        "real_social_screenshot_auto_crop",
        "real_colorful_poster_no_card",
        "real_busy_poster_wall_no_card",
        "real_warm_indoor_light_no_card",
        "real_screen_cool_light_no_card",
        "real_clear_glasses",
        "real_bangs_forehead",
        "real_hand_near_face",
        "card_fake_grid",
        "portrait_sunglasses",
    ]
    dollar_count = html.count("const $ = (id) => document.getElementById(id);")
    dollar_pos = html.find("const $ = (id) => document.getElementById(id);")
    esc_pos = html.find("const esc =")
    render_result_pos = html.find("function renderResult")
    render_next_actions_pos = html.find("function renderNextActions")
    friendly_transport_pos = html.find("function friendlyTransportError")
    return [
        _check("Demo 页面包含真实上传快捷样本", all(case_id in html for case_id in required_cases), required_cases),
        _check("Demo 页面包含用户可理解样本标签", all(label in html for label in ["春季样例", "夏季样例", "秋季样例", "冬季样例", "App截图", "彩色背景", "海报墙", "室内暖光", "屏幕冷光", "普通眼镜", "刘海遮额", "手托脸", "伪色卡", "遮挡重拍"]), None),
        _check("Demo 页面不引用 QA 统计变量", "renderSeasonalAccuracy(data." not in html, None),
        _check("Demo 页面只定义一次元素选择器", dollar_count == 1, dollar_count),
        _check("Demo 页面选择器在事件绑定前可用", 0 <= dollar_pos < html.find("function setSeason"), {"dollar_pos": dollar_pos}),
        _check("Demo 页面转义函数在结果渲染前可用", 0 <= esc_pos < render_result_pos and esc_pos < render_next_actions_pos and esc_pos < friendly_transport_pos, {"esc_pos": esc_pos, "render_result_pos": render_result_pos}),
        _check("Demo 页面绑定所有样本点击", "fixtureCaseLabels" in html and "const initialCase" in html, None),
        _check("Demo 页面校验分享样本链接", 'new URLSearchParams(window.location.search).get("case")' in html, None),
        _check("Demo 页面无效样本链接给出友好提示", "当前页面已切换为真实上传流程" in html, None),
        _check("Demo 页面区分接口失败和渲染失败", "Color demo result render failed" in html and "结果整理失败" in html, None),
    ]


def evaluate_case_payload(case_id: str, expected_tier: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    summary = payload.get("result_summary") or {}
    capture = summary.get("capture") or {}
    actual_tier = capture.get("result_tier")
    checks = [
        _check(f"{case_id} 结果层级为 {expected_tier}", actual_tier == expected_tier, actual_tier),
    ]
    if expected_tier == "retake":
        checks.append(_check(f"{case_id} 不展示色彩结果", summary.get("available") is False, summary))
        checks.append(_check(f"{case_id} 状态 needs_retake", payload.get("status") == "needs_retake", payload.get("status")))
    else:
        checks.append(_check(f"{case_id} 可展示色彩结果", summary.get("available") is True, summary))
        checks.append(_check(f"{case_id} 状态 analyzed", payload.get("status") == "analyzed", payload.get("status")))
    return checks


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    return json.loads(_get_text(url, timeout))


def _get_text(url: str, timeout: float) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed: {url}: {exc}") from exc


def _check(name: str, passed: bool, evidence: Any = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
    }


if __name__ == "__main__":
    main()

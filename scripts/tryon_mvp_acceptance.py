from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tryon import (
    TRYON_MODEL_FIXTURE_DIR,
    TRYON_OUTPUT_DIR,
    MockTryOnProvider,
    OpenAIImageEditTryOnProvider,
    _extract_top_from_note_image,
    _read_upload_image,
    run_try_on,
    tryon_capabilities,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "images"
LOCAL_REPORT_PATH = ROOT / "outputs" / "tryon_mvp_acceptance.json"
EXTERNAL_REPORT_PATH = ROOT / "outputs" / "tryon_mvp_external_acceptance.json"


def _load_upload(path: Path, role: str) -> dict:
    return _read_upload_image(path.read_bytes(), path.name, role)


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#f7f2f4")
    pixels = image.load()
    for y in range(180, 760):
        width = 210 + int((y - 180) * 0.12)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60, 105)
    return image


def _case(name: str, passed: bool, evidence: dict) -> dict:
    return {"name": name, "passed": passed, "evidence": evidence}


def _parse_args() -> object:
    parser = ArgumentParser(description="Run AI try-on MVP acceptance checks.")
    parser.add_argument(
        "--require-external",
        action="store_true",
        help="Production gate: fail unless an OpenAI-compatible images.edit provider returns a generated result.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional output path for the acceptance JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cases: list[dict] = []

    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_acceptance")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_acceptance")
    result = run_try_on(person, garment, MockTryOnProvider())
    cases.append(_case(
        "default_model_generates_tryon",
        result["status"] == "generated" and bool(result["result"]["image_path"]),
        {
            "status": result["status"],
            "input_quality": result["pipeline"]["input_quality"]["status"],
            "garment_provider": result["pipeline"]["garment_analysis"]["evidence"].get("provider"),
            "image_provider": result["pipeline"]["image_edit"]["evidence"].get("provider"),
            "image_path": result["result"]["image_path"],
        },
    ))

    work_dir = TRYON_OUTPUT_DIR / "acceptance"
    work_dir.mkdir(parents=True, exist_ok=True)

    top_image = _synthetic_top_image()
    top_source = work_dir / "synthetic_top.png"
    top_image.save(top_source)
    top_item = _extract_top_from_note_image(
        {"url": "https://sns-webpic-qc.xhscdn.com/synthetic_top.png", "image": top_image, "source_path": top_source},
        0,
        work_dir,
    )
    cases.append(_case(
        "single_garment_without_face_is_extracted",
        top_item["has_top"] and top_item["reason"] == "single_garment_top" and bool(top_item["cutout_path"]),
        {"reason": top_item["reason"], "cutout_path": top_item["cutout_path"], "crop_box": top_item["crop_box"]},
    ))

    blank = Image.new("RGB", (720, 900), "#f7f2f4")
    blank_source = work_dir / "blank.png"
    blank.save(blank_source)
    blank_item = _extract_top_from_note_image(
        {"url": "https://sns-webpic-qc.xhscdn.com/blank.png", "image": blank, "source_path": blank_source},
        1,
        work_dir,
    )
    cases.append(_case(
        "image_without_top_is_rejected",
        not blank_item["has_top"] and blank_item["cutout_path"] is None,
        {"reason": blank_item["reason"], "garment_status": blank_item["garment_analysis"]["status"]},
    ))

    capabilities = tryon_capabilities()
    openai_base_url = capabilities["provider"]["base_url"]
    compatible_ready = capabilities["checks"]["openai_compatible_text_or_vision"]
    external_ready = capabilities["checks"]["openai_compatible_images_edit"] or capabilities["provider"]["api_key_present"]
    if external_ready:
        external_result = run_try_on(person, garment, OpenAIImageEditTryOnProvider())
        external_passed = external_result["status"] == "generated" and bool(external_result["result"]["image_path"])
        cases.append(_case(
            "real_openai_image_edit_generates_tryon",
            external_passed,
            {
                "openai_compatible_provider_present": True,
                "openai_image_edit_provider_present": True,
                "openai_api_key_present": capabilities["provider"]["api_key_present"],
                "openai_base_url": openai_base_url,
                "capabilities": capabilities,
                "status": external_result["status"],
                "image_provider": external_result["pipeline"]["image_edit"]["evidence"].get("provider"),
                "model": external_result["pipeline"]["image_edit"]["evidence"].get("model"),
                "error": external_result["pipeline"]["image_edit"]["evidence"].get("error"),
                "image_path": external_result["result"]["image_path"],
                "user_message": external_result["result"]["user_message"],
            },
        ))
    else:
        cases.append(_case(
            "real_openai_image_edit_generates_tryon",
            False,
            {
                "openai_compatible_provider_present": compatible_ready,
                "openai_image_edit_provider_present": False,
                "openai_api_key_present": capabilities["provider"]["api_key_present"],
                "openai_base_url": openai_base_url,
                "capabilities": capabilities,
                "note": "真实图像编辑需要支持 images.edit 的 OpenAI 兼容本地代理或 key；当前只验收本地 mock 链路。",
            },
        ))

    external_case = next(case for case in cases if case["name"] == "real_openai_image_edit_generates_tryon")
    required_cases = [case for case in cases if case is not external_case]
    local_passed = all(case["passed"] for case in required_cases)
    external_passed = external_case["passed"]
    passed = local_passed and (external_passed or not args.require_external)
    report_status = (
        "passed"
        if local_passed and external_passed
        else "passed_for_validation"
        if local_passed and not args.require_external
        else "failed"
    )
    report = {
        "status": report_status,
        "summary": {
            "passed": sum(1 for case in cases if case["passed"]),
            "total": len(cases),
            "required_passed": sum(1 for case in required_cases if case["passed"]),
            "required_total": len(required_cases),
            "require_external": args.require_external,
            "validation_ready": local_passed,
            "production_image_edit_ready": external_passed,
        },
        "cases": cases,
    }
    report_path = args.report_path or (EXTERNAL_REPORT_PATH if args.require_external else LOCAL_REPORT_PATH)
    report["report_path"] = str(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

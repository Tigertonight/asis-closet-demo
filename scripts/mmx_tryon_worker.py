from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.tryon import CODEX_BRIDGE_DIR, complete_codex_bridge_job, _write_json_atomically  # noqa: E402


def _load_job(job_id: str) -> dict:
    job_path = CODEX_BRIDGE_DIR / f"{job_id}.json"
    if not job_path.exists():
        raise FileNotFoundError(f"job not found: {job_id}")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["job_path"] = str(job_path)
    return job


def _save_job(job: dict) -> None:
    job_path = Path(job["job_path"])
    payload = {key: value for key, value in job.items() if key != "job_path"}
    _write_json_atomically(job_path, payload)


def _mark_failed(job: dict, message: str) -> dict:
    job["status"] = "failed"
    job.setdefault("result", {})["message"] = message
    _save_job(job)
    return job


def _mmx_prompt(job: dict) -> str:
    original = job.get("prompt", "")
    garment_hint = ""
    marker = "The target garment is "
    if marker in original:
        garment_hint = original.split(marker, 1)[1].split("Do not alter", 1)[0].strip()
    if not garment_hint:
        garment_hint = "the uploaded target upper garment, matching its color, fabric, sleeve length, neckline, and fit"
    return (
        "Realistic upper-body virtual try-on photo. "
        "Use the referenced person as identity anchor: keep face, hair, skin tone, body shape, pose, arms, gray studio background, lighting, and camera angle. "
        "Change only the upper-body clothing. "
        f"Target garment: {garment_hint} "
        "Natural fabric folds, clean consumer fashion app result. No UI, no watermark, no extra objects."
    )


def process_job(job_id: str) -> dict:
    job = _load_job(job_id)
    if job.get("status") == "completed":
        return job
    if job.get("status") not in {"pending", "running", "failed"}:
        return job

    person_image = Path(job["input"]["person_image_path"])
    target_path = Path(job["result"]["target_path"])
    target_path.parent.mkdir(parents=True, exist_ok=True)

    job["status"] = "running"
    job["provider"] = "mmx_cli_worker"
    job.setdefault("result", {})["message"] = "MiniMax 本地后台正在生成试穿图。"
    _save_job(job)

    cmd = [
        "mmx",
        "image",
        "generate",
        "--prompt",
        _mmx_prompt(job),
        "--subject-ref",
        f"type=character,image={person_image}",
        "--width",
        "1024",
        "--height",
        "1536",
        "--out",
        str(target_path),
        "--output",
        "json",
        "--quiet",
        "--non-interactive",
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            timeout=360,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _mark_failed(job, "MiniMax 生成超时，请稍后重试。")

    job["mmx"] = {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }
    _save_job(job)
    if completed.returncode != 0:
        return _mark_failed(job, "MiniMax 生成失败，请检查 mmx auth 或稍后重试。")

    return complete_codex_bridge_job(job_id, target_path)


def pending_jobs() -> list[str]:
    CODEX_BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    job_ids = []
    for path in sorted(CODEX_BRIDGE_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if job.get("status") == "pending":
            job_ids.append(job.get("job_id") or path.stem)
    return job_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume local try-on bridge jobs with mmx image generation.")
    parser.add_argument("--job-id", help="Process one bridge job id.")
    parser.add_argument("--once", action="store_true", help="Process the next pending job once.")
    args = parser.parse_args()

    if args.job_id:
        print(json.dumps(process_job(args.job_id), ensure_ascii=False, indent=2))
        return 0

    ids = pending_jobs()
    if args.once:
        ids = ids[:1]
    results = [process_job(job_id) for job_id in ids]
    print(json.dumps({"processed": len(results), "jobs": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

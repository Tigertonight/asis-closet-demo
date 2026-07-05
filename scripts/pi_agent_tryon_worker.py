from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT_DIR / "outputs" / "tryon" / "codex_bridge"
DEFAULT_PROVIDER = os.getenv("PI_TRYON_PROVIDER", "openai-codex")
DEFAULT_MODEL = os.getenv("PI_TRYON_MODEL", "gpt-5.5")
DEFAULT_TIMEOUT = int(os.getenv("PI_TRYON_TIMEOUT", "300"))
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Process try-on bridge jobs with local Pi/Diga GPT image generation.")
    parser.add_argument("--once", action="store_true", help="Process one scan and exit.")
    parser.add_argument("--interval", type=float, default=3.0, help="Polling interval in seconds.")
    parser.add_argument("--limit", type=int, default=1, help="Max jobs to process per scan.")
    parser.add_argument("--job-id", help="Only process one bridge job id.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call Pi; only print eligible jobs.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="Pi provider name.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Pi model name.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-job timeout in seconds.")
    args = parser.parse_args()

    while True:
        processed = process_scan(args)
        if args.once:
            return 0 if processed >= 0 else 1
        time.sleep(args.interval)


def process_scan(args: argparse.Namespace) -> int:
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in sorted(BRIDGE_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime):
        if args.job_id and path.stem != args.job_id:
            continue
        job = read_json(path)
        if job.get("status") in {"pending", "worker_waiting_provider"}:
            jobs.append((path, job))
        if len(jobs) >= args.limit:
            break

    if args.dry_run:
        for path, job in jobs:
            print(json.dumps({"job_id": job.get("job_id"), "status": job.get("status"), "path": str(path)}, ensure_ascii=False))
        return len(jobs)

    if not jobs:
        print("No pending bridge jobs.")
        return 0

    if not pi_ready():
        for path, job in jobs:
            mark_failed(path, job, "本机没有找到 pi 命令，无法调用 Diga/Pi Agent。")
        return 0

    ok = 0
    for path, job in jobs:
        try:
            process_job(path, job, args.provider, args.model, args.timeout)
            print(f"{job.get('job_id')}: completed")
            ok += 1
        except Exception as exc:
            mark_failed(path, job, str(exc))
            print(f"{job.get('job_id')}: failed: {exc}", file=sys.stderr)
    return ok


def pi_ready() -> bool:
    return shutil.which("pi") is not None


def process_job(path: Path, job: dict[str, Any], provider: str, model: str, timeout: int) -> None:
    job["status"] = "running"
    job.setdefault("worker", {})["name"] = "pi_agent_tryon_worker"
    job["worker"]["provider"] = provider
    job["worker"]["model"] = model
    job["worker"]["started_at"] = int(time.time())
    write_json(path, job)

    target_path = Path(job["result"]["target_path"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    person_path = Path(job["input"]["person_image_path"])
    garment_path = Path(job["input"]["garment_image_path"])
    prompt = build_worker_prompt(job, target_path.name)
    start_time = time.time()

    cmd = [
        "pi",
        "--provider",
        provider,
        "--model",
        model,
        "--no-session",
        "-p",
        f"@{person_path}",
        f"@{garment_path}",
        prompt,
    ]
    returncode, command_output = run_pi_command_until_image(cmd, target_path.parent, target_path, start_time, timeout)
    job.setdefault("worker", {})["command_output"] = command_output[-4000:]
    if returncode != 0 and not target_path.exists():
        write_json(path, job)
        raise RuntimeError(f"Pi Agent exited {returncode}: {command_output[-1200:]}")

    generated_path = find_generated_image(command_output, target_path.parent, start_time)
    if generated_path is None:
        write_json(path, job)
        raise RuntimeError(f"Pi Agent finished but no generated image was found. Output: {command_output[-1200:]}")

    normalize_to_target(generated_path, target_path)
    with Image.open(target_path) as image:
        image.verify()

    job["status"] = "completed"
    job["result"]["image_path"] = str(target_path)
    job["result"]["public_image_path"] = public_tryon_path(target_path)
    job["result"]["message"] = "本地 Diga/Pi Agent 已自动回填试穿结果。"
    job["worker"]["generated_path"] = str(generated_path)
    job["worker"]["completed_at"] = int(time.time())
    write_json(path, job)


def run_pi_command_until_image(cmd: list[str], cwd: Path, target_path: Path, started_at: float, timeout: int) -> tuple[int, str]:
    stdout_path = cwd / ".pi_agent_stdout.log"
    with stdout_path.open("w+", encoding="utf-8", errors="ignore") as output:
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        stable_size = -1
        stable_ticks = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            if process.poll() is not None:
                break
            if image_ready(target_path, started_at):
                current_size = target_path.stat().st_size
                if current_size == stable_size:
                    stable_ticks += 1
                else:
                    stable_size = current_size
                    stable_ticks = 0
                if stable_ticks >= 2:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    break
            time.sleep(2)
        else:
            process.kill()
            process.wait(timeout=5)

        output.flush()
        output.seek(0)
        command_output = output.read()
        return process.returncode if process.returncode is not None else 0, command_output


def image_ready(path: Path, started_at: float) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if path.stat().st_mtime + 0.001 < started_at:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def build_worker_prompt(job: dict[str, Any], target_filename: str) -> str:
    return (
        "You are given two images. Image A is the target person/model photo. Image B is the clothing reference photo. "
        "Generate one realistic virtual try-on image: make the person in Image A wear the upper-body garment from Image B. "
        "Use Image A as the base image. Preserve the person's face, hair, skin tone, body shape, arms, pose, camera angle, lighting, and background. "
        "Only replace the upper-body clothing. Match Image B's garment color, material, neckline, sleeve length, structure, logo/print, and visible details as closely as possible. "
        "The final garment must be opaque, naturally fitted to the body, and integrated with realistic folds, seams, shadows, and occlusion around the neck, shoulders, arms, hair, and hands. "
        "Do not leave the original shirt visible under the replaced garment unless it would naturally be visible at the collar or hem. "
        "Do not output a comparison, collage, reference board, labels, UI, watermark, or extra objects. "
        f"Save the final generated image in the current working directory as `{target_filename}` if possible."
    )


def find_generated_image(stdout: str, work_dir: Path, started_at: float) -> Path | None:
    saved_matches = re.findall(r"Saved:\s*`([^`]+)`", stdout)
    for raw in reversed(saved_matches):
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = work_dir / candidate
        if candidate.exists() and candidate.suffix.lower() in IMAGE_SUFFIXES:
            return candidate

    candidates = []
    for candidate in work_dir.iterdir():
        if candidate.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if candidate.stat().st_mtime + 0.001 >= started_at:
            candidates.append(candidate)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def normalize_to_target(source_path: Path, target_path: Path) -> None:
    if source_path.resolve() == target_path.resolve():
        return
    with Image.open(source_path) as image:
        image.convert("RGB").save(target_path, "PNG")


def mark_failed(path: Path, job: dict[str, Any], message: str) -> None:
    try:
        latest = read_json(path)
        if latest.get("status") == "completed":
            return
    except Exception:
        pass
    job["status"] = "failed"
    job.setdefault("worker", {})["name"] = "pi_agent_tryon_worker"
    job["worker"]["failed_at"] = int(time.time())
    job["worker"]["error"] = message
    job.setdefault("result", {})["message"] = "本地 Diga/Pi Agent 生成失败，请稍后重试。"
    write_json(path, job)


def public_tryon_path(path: Path) -> str:
    output_root = ROOT_DIR / "outputs" / "tryon"
    return "/tryon-outputs/" + path.relative_to(output_root).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8002"


def _get_json(url: str, timeout: float = 10.0) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: float = 90.0) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        body = getattr(exc, "read", lambda: b"")()
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {"raw": body.decode("utf-8", errors="ignore") if body else ""}
        data.setdefault("transport_error", str(exc))
        return getattr(exc, "code", 0) or 0, data


def _baseline_ready(readiness: dict) -> bool:
    ready = readiness.get("ready", {})
    endpoints = readiness.get("endpoints", {})
    return bool(
        ready.get("base_app")
        and ready.get("multi_category_closet")
        and ready.get("edge_refine")
        and ready.get("real_tryon")
        and ready.get("xhs_search")
        and endpoints.get("stylist_bridge_health", {}).get("reachable")
        and endpoints.get("stylist_memory", {}).get("reachable")
    )


def _wait_for_readiness(base_url: str, deadline: float, strict: bool = False) -> dict:
    last_error = ""
    last_readiness: dict | None = None
    while time.time() < deadline:
        try:
            last_readiness = _get_json(f"{base_url.rstrip('/')}/asis/runtime-readiness")
            if strict:
                if last_readiness.get("status") == "ready_for_full_user_trial":
                    return last_readiness
            elif _baseline_ready(last_readiness):
                return last_readiness
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1)
    if last_readiness is not None:
        return last_readiness
    raise RuntimeError(f"runtime readiness did not become available: {last_error}")


def _run_smoke(base_url: str) -> dict:
    proc = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/asis_runtime_smoke.py"), base_url],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"status": "failed", "stdout": proc.stdout, "stderr": proc.stderr}
    data["returncode"] = proc.returncode
    return data


def _probe_memory(base_url: str) -> dict:
    try:
        data = _get_json(f"{base_url.rstrip('/')}/stylist/memory?user_id=acceptance-user", timeout=15)
        return {
            "passed": data.get("status") == "ok",
            "status": data.get("status"),
            "memory_count": len(data.get("memory", [])) if isinstance(data.get("memory"), list) else None,
            "error_code": data.get("error", {}).get("code") if isinstance(data.get("error"), dict) else None,
        }
    except Exception as exc:
        return {"passed": False, "error": str(exc)}


def _probe_ai_chat(base_url: str) -> dict:
    status, data = _post_json(
        f"{base_url.rstrip('/')}/stylist/chat",
        {
            "message": "请用一句话给我一条适合通勤的穿搭建议。",
            "session_id": "acceptance",
            "user_id": "acceptance-user",
        },
        timeout=120,
    )
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    return {
        "passed": status < 400 and data.get("status") == "ok",
        "http_status": status,
        "status": data.get("status"),
        "mode": data.get("mode"),
        "error_code": error.get("code"),
        "assistant_message_present": bool(str(data.get("assistant_message") or "").strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and verify the asis full local stack.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--strict", action="store_true", help="Require ready_for_full_user_trial.")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--keep-running", action="store_true", help="Leave services running after checks.")
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("APP_PORT", args.base_url.rsplit(":", 1)[-1] if ":" in args.base_url else "8002")
    proc = subprocess.Popen(
        [str(ROOT / "scripts/start_asis_full_stack.sh")],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )
    started_at = time.time()
    result: dict[str, object] = {
        "status": "failed",
        "base_url": args.base_url,
        "strict": args.strict,
        "checks": [],
    }
    try:
        readiness = _wait_for_readiness(args.base_url, started_at + args.timeout, strict=args.strict)
        smoke = _run_smoke(args.base_url)
        memory_probe = _probe_memory(args.base_url) if args.strict else {"passed": True, "skipped": True}
        ai_probe = _probe_ai_chat(args.base_url) if args.strict else {"passed": True, "skipped": True}
        result["readiness"] = readiness
        result["smoke"] = smoke
        result["memory_probe"] = memory_probe
        result["ai_probe"] = ai_probe
        result["checks"] = [
            {"name": "runtime_readiness_endpoint", "passed": True},
            {"name": "baseline_full_stack", "passed": _baseline_ready(readiness)},
            {"name": "runtime_smoke", "passed": smoke.get("status") == "passed"},
            {
                "name": "strict_full_user_trial",
                "passed": readiness.get("status") == "ready_for_full_user_trial",
                "required": args.strict,
            },
            {
                "name": "strict_memory_proxy",
                "passed": bool(memory_probe.get("passed")),
                "required": args.strict,
            },
            {
                "name": "strict_ai_stylist_chat",
                "passed": bool(ai_probe.get("passed")),
                "required": args.strict,
            },
        ]
        required_checks = [check for check in result["checks"] if check.get("required", True)]
        result["status"] = "passed" if all(check["passed"] for check in required_checks) else "failed"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    finally:
        if not args.keep_running:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
                proc.wait(timeout=8)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

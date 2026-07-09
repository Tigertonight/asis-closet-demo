from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_runtime_readiness import readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until required demo runtime dependencies are ready.")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--require-sidecars", action="store_true")
    parser.add_argument("--env", type=Path, default=None)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    last_report: dict[str, object] | None = None
    while time.monotonic() < deadline:
        report = readiness(args.env)
        last_report = report
        ready = report.get("ready", {})
        base_ready = bool(ready.get("base_app") and ready.get("real_tryon"))
        sidecars_ready = bool(ready.get("ai_stylist") and ready.get("xhs_search")) if args.require_sidecars else True
        if base_ready and sidecars_ready:
            print(json.dumps({"status": "ready", "ready": ready}, ensure_ascii=False, indent=2))
            return 0
        time.sleep(args.interval)

    print(json.dumps({"status": "timeout", "last_report": last_report}, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

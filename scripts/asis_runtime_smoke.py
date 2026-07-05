from __future__ import annotations

import json
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8002"


def _get_json(path: str, timeout: float = 60.0) -> dict:
    with urlopen(f"{BASE_URL}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    checks = []
    for path in ["/asis/runtime-readiness", "/closet/capabilities", "/stylist/capabilities"]:
        try:
            data = _get_json(path)
            checks.append({"path": path, "passed": True, "status": data.get("status") or data.get("mode") or "ok"})
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            checks.append({"path": path, "passed": False, "error": str(exc)})
    readiness = next((check for check in checks if check["path"] == "/asis/runtime-readiness"), {})
    result = {
        "status": "passed" if all(check["passed"] for check in checks) else "failed",
        "base_url": BASE_URL,
        "checks": checks,
        "checked_at": time.time(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

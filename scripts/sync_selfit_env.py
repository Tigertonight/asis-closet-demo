from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"

DEFAULTS = {
    "STYLIST_OPENCLAW_CHAT_URL": "http://127.0.0.1:18789/api/selfit/chat",
    "STYLIST_OPENCLAW_MEMORY_URL": "http://127.0.0.1:18789/api/selfit/memory",
    "STYLIST_OPENCLAW_AGENT_ID": "selfit-stylist",
    "STYLIST_SELFIT_TOOL_BASE_URL": "http://127.0.0.1:8002",
    "STYLIST_OPENCLAW_TIMEOUT": "180",
    "STYLIST_OPENCLAW_MODEL": "minimax-portal/MiniMax-M3",
    "STYLIST_DEMO_MODE": "0",
    "SELFIT_OPENCLAW_BRIDGE_HOST": "127.0.0.1",
    "SELFIT_OPENCLAW_BRIDGE_PORT": "18789",
    "SELFIT_XHS_MCP_URL": "http://127.0.0.1:18060/mcp",
    "SELFIT_XHS_MCP_MODE": "streamable-http",
    "SELFIT_XHS_ALLOWED_TOOLS": "check_login_status,search_feeds,get_feed_detail,list_feeds",
    "SELFIT_SEGFORMER_MODEL": "mattmdjaga/segformer_b2_clothes",
    "SELFIT_SEGFORMER_DEVICE": "auto",
    "SELFIT_REMBG_ENABLED": "1",
    "SELFIT_ONBOARDING_SESSION_TTL_HOURS": "24",
    "MINIMAX_API_KEY": "",
    "MINIMAX_OAUTH_TOKEN": "",
}


def _parse_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def sync_env(path: Path = DEFAULT_ENV) -> dict[str, object]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = _parse_keys(text)
    missing = [(key, value) for key, value in DEFAULTS.items() if key not in existing]
    if missing:
        lines = []
        if text and not text.endswith("\n"):
            lines.append("")
        lines.append("")
        lines.append("# selfit runtime defaults (non-secret)")
        lines.extend(f"{key}={value}" for key, value in missing)
        path.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(path), "added": [key for key, _ in missing], "kept_existing": sorted(existing)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append non-secret selfit runtime defaults to .env without overwriting keys.")
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="Path to .env file.")
    args = parser.parse_args()
    result = sync_env(Path(args.env))
    print(f"Updated {result['path']}")
    if result["added"]:
        print("Added:")
        for key in result["added"]:
            print(f"  {key}")
    else:
        print("No missing selfit runtime defaults.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SELFIT_RUNTIME_ROOT = ROOT / "selfit-agent-runtime"
DEFAULT_STYLIST_MODEL = "openai/gpt-5.5"
STYLIST_MODEL_KEY_ENV_BY_PROVIDER = {
    "openai": ["OPENAI_API_KEY", "STYLIST_OPENCLAW_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "google-gemini-cli": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "google-vertex": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "dashscope": ["DASHSCOPE_API_KEY"],
    "moonshot": ["MOONSHOT_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
    "minimax-cn": ["MINIMAX_API_KEY"],
    "minimax-portal": ["MINIMAX_OAUTH_TOKEN", "MINIMAX_API_KEY"],
    "minimax-portal-cn": ["MINIMAX_OAUTH_TOKEN", "MINIMAX_API_KEY"],
}


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _stylist_model_ref() -> str:
    return os.environ.get("STYLIST_OPENCLAW_MODEL", "").strip() or DEFAULT_STYLIST_MODEL


def _stylist_model_provider(model_ref: str | None = None) -> str:
    ref = (model_ref or _stylist_model_ref()).strip().lower()
    return ref.split("/", 1)[0] if "/" in ref else "openai"


def _stylist_model_key_names() -> list[str]:
    names: list[str] = []
    for values in STYLIST_MODEL_KEY_ENV_BY_PROVIDER.values():
        names.extend(values)
    return sorted(set(names))


def _stylist_key_report() -> dict[str, object]:
    model = _stylist_model_ref()
    provider = _stylist_model_provider(model)
    accepted_keys = STYLIST_MODEL_KEY_ENV_BY_PROVIDER.get(provider, [])
    any_key_present = any(_env_present(key) for key in _stylist_model_key_names())
    matching_key_present = any(_env_present(key) for key in accepted_keys)
    return {
        "model": model,
        "provider": provider,
        "accepted_env_keys": accepted_keys,
        "any_key_present": any_key_present,
        "matching_key_present": matching_key_present,
    }


def _http_probe(url: str | None, timeout: float = 2.0) -> dict[str, object]:
    if not url:
        return {"configured": False, "reachable": False}
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return {"configured": True, "reachable": True, "status_code": response.status}
    except HTTPError as exc:
        return {"configured": True, "reachable": True, "status_code": exc.code, "http_error": exc.reason}
    except URLError as exc:
        return {"configured": True, "reachable": False, "error": str(exc.reason)}
    except Exception as exc:
        return {"configured": True, "reachable": False, "error": str(exc)}


def _bridge_health_url(chat_url: str | None) -> str | None:
    if not chat_url:
        return None
    for suffix in ["/api/selfit/chat", "/api/chat", "/chat"]:
        if chat_url.endswith(suffix):
            return chat_url[: -len(suffix)] + "/health"
    return chat_url.rstrip("/") + "/health"


def readiness(env_path: Path | None = None) -> dict[str, object]:
    load_dotenv(env_path or ROOT / ".env", override=True)
    stylist_key = _stylist_key_report()
    modules = {
        "base": {
            "PIL": _module_available("PIL"),
            "numpy": _module_available("numpy"),
            "cv2": _module_available("cv2"),
            "mediapipe": _module_available("mediapipe"),
            "httpx": _module_available("httpx"),
            "openai": _module_available("openai"),
        },
        "closet_segmentation": {
            "torch": _module_available("torch"),
            "transformers": _module_available("transformers"),
        },
        "matting": {
            "rembg": _module_available("rembg"),
            "onnxruntime": _module_available("onnxruntime"),
        },
    }
    env = {
        "tryon": {
            "openai_base_url": _env_present("TRYON_OPENAI_BASE_URL") or _env_present("OPENAI_BASE_URL"),
            "openai_api_key": _env_present("TRYON_OPENAI_API_KEY") or _env_present("OPENAI_API_KEY"),
            "runway_google_url": _env_present("TRYON_RUNWAY_GOOGLE_URL") or _env_present("RUNWAY_GOOGLE_URL"),
            "runway_google_api_key": _env_present("TRYON_RUNWAY_GOOGLE_API_KEY") or _env_present("RUNWAY_GOOGLE_API_KEY") or _env_present("REDNOTE_RUNWAY_API_KEY"),
        },
        "stylist": {
            "chat_url": _env_present("STYLIST_OPENCLAW_CHAT_URL") or _env_present("OPENCLAW_SELFIT_CHAT_URL"),
            "memory_url": _env_present("STYLIST_OPENCLAW_MEMORY_URL"),
            "model": stylist_key["model"],
            "model_provider": stylist_key["provider"],
            "model_key_present": stylist_key["any_key_present"],
            "model_key_matches_provider": stylist_key["matching_key_present"],
            "accepted_model_key_env": stylist_key["accepted_env_keys"],
            "demo_mode": os.environ.get("STYLIST_DEMO_MODE", "").strip() in {"1", "true", "yes", "on"},
        },
        "xiaohongshu": {
            "mcp_url": _env_present("SELFIT_XHS_MCP_URL") or _env_present("STYLIST_XHS_MCP_URL"),
            "allowed_tools": os.environ.get("SELFIT_XHS_ALLOWED_TOOLS") or os.environ.get("STYLIST_XHS_ALLOWED_TOOLS") or "",
        },
        "birefnet": {
            "endpoint": _env_present("SELFIT_BIREFNET_ENDPOINT"),
            "model": _env_present("SELFIT_BIREFNET_MODEL"),
        },
    }
    stylist_chat_url = os.environ.get("STYLIST_OPENCLAW_CHAT_URL") or os.environ.get("OPENCLAW_SELFIT_CHAT_URL")
    xhs_mcp_url = os.environ.get("SELFIT_XHS_MCP_URL") or os.environ.get("STYLIST_XHS_MCP_URL")
    endpoints = {
        "stylist_bridge_health": _http_probe(_bridge_health_url(stylist_chat_url)),
        "stylist_chat": {"configured": bool(stylist_chat_url), "reachable": bool(stylist_chat_url), "method": "POST"},
        "stylist_memory": _http_probe(os.environ.get("STYLIST_OPENCLAW_MEMORY_URL")),
        "xiaohongshu_mcp": _http_probe(xhs_mcp_url),
        "tryon_openai_base": _http_probe(os.environ.get("TRYON_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")),
    }
    sidecars = {
        "openclaw": {
            "source_present": (SELFIT_RUNTIME_ROOT / "vendor" / "openclaw").exists(),
            "built": (SELFIT_RUNTIME_ROOT / "vendor" / "openclaw" / "dist" / "entry.mjs").exists()
            or (SELFIT_RUNTIME_ROOT / "vendor" / "openclaw" / "dist" / "entry.js").exists(),
            "lock_present": (SELFIT_RUNTIME_ROOT / "openclaw.lock.json").exists(),
            "bridge_script_present": (SELFIT_RUNTIME_ROOT / "scripts" / "selfit-openclaw-bridge.mjs").exists(),
            "config_present": (SELFIT_RUNTIME_ROOT / "config" / "openclaw.local.json").exists(),
            "workspace_identity_present": (SELFIT_RUNTIME_ROOT / "AGENTS.md").exists(),
            "workspace_tools_present": (SELFIT_RUNTIME_ROOT / "TOOLS.md").exists(),
            "workspace_personality_present": (SELFIT_RUNTIME_ROOT / "SOUL.md").exists(),
            "tool_spec_present": (SELFIT_RUNTIME_ROOT / "tools" / "selfit-tools.openapi.json").exists(),
            "agent_prompt_present": (SELFIT_RUNTIME_ROOT / "agents" / "selfit-stylist" / "agent.md").exists(),
        },
        "xiaohongshu_mcp": {
            "source_present": (SELFIT_RUNTIME_ROOT / "vendor" / "xiaohongshu-mcp").exists(),
            "lock_present": (SELFIT_RUNTIME_ROOT / "xiaohongshu-mcp.lock.json").exists(),
            "docker_available": shutil.which("docker") is not None,
            "go_available": shutil.which("go") is not None,
            "vendored_go_available": (SELFIT_RUNTIME_ROOT / "vendor" / "toolchains" / "go" / "bin" / "go").exists(),
            "go_runtime_lock_present": (SELFIT_RUNTIME_ROOT / "go-runtime.lock.json").exists(),
            "docker_compose_present": (SELFIT_RUNTIME_ROOT / "vendor" / "xiaohongshu-mcp" / "docker" / "docker-compose.yml").exists(),
            "go_start_script_present": (SELFIT_RUNTIME_ROOT / "scripts" / "start-xhs-mcp-go.sh").exists(),
        },
    }
    openclaw_static_ready = all(
        bool(sidecars["openclaw"][key])
        for key in [
            "source_present",
            "built",
            "lock_present",
            "bridge_script_present",
            "config_present",
            "workspace_identity_present",
            "workspace_tools_present",
            "workspace_personality_present",
            "tool_spec_present",
            "agent_prompt_present",
        ]
    )
    ready = {
        "base_app": all(modules["base"].values()),
        "multi_category_closet": modules["closet_segmentation"]["torch"] and modules["closet_segmentation"]["transformers"],
        "edge_refine": modules["matting"]["rembg"] and modules["matting"]["onnxruntime"],
        "ai_stylist": env["stylist"]["chat_url"]
        and env["stylist"]["memory_url"]
        and openclaw_static_ready
        and endpoints["stylist_bridge_health"]["reachable"]
        and endpoints["stylist_memory"]["reachable"]
        and env["stylist"]["model_key_matches_provider"]
        and not env["stylist"]["demo_mode"],
        "xhs_search": env["xiaohongshu"]["mcp_url"]
        and sidecars["xiaohongshu_mcp"]["source_present"]
        and endpoints["xiaohongshu_mcp"]["reachable"]
        and (
            sidecars["xiaohongshu_mcp"]["docker_available"]
            or sidecars["xiaohongshu_mcp"]["go_available"]
            or sidecars["xiaohongshu_mcp"]["vendored_go_available"]
        ),
        "real_tryon": (env["tryon"]["openai_base_url"] and env["tryon"]["openai_api_key"]) or (env["tryon"]["runway_google_url"] and env["tryon"]["runway_google_api_key"]),
    }
    missing_actions = []
    if not ready["multi_category_closet"]:
        missing_actions.append("Install requirements-ai.txt to enable torch + transformers for SegFormer clothes parsing.")
    if not ready["edge_refine"]:
        missing_actions.append("Install requirements-ai.txt to enable rembg + onnxruntime for cleaner transparent PNG edges.")
    if not sidecars["openclaw"]["built"]:
        missing_actions.append("Build OpenClaw with selfit-agent-runtime/scripts/build-openclaw.sh.")
    if not sidecars["openclaw"]["config_present"]:
        missing_actions.append("Create selfit-agent-runtime/config/openclaw.local.json for the selfit-stylist OpenClaw workspace.")
    if not (sidecars["openclaw"]["workspace_identity_present"] and sidecars["openclaw"]["workspace_tools_present"] and sidecars["openclaw"]["tool_spec_present"]):
        missing_actions.append("Add selfit OpenClaw workspace files AGENTS.md, TOOLS.md, and tools/selfit-tools.openapi.json.")
    if not (
        env["stylist"]["chat_url"]
        and env["stylist"]["memory_url"]
        and openclaw_static_ready
        and endpoints["stylist_bridge_health"]["reachable"]
        and endpoints["stylist_memory"]["reachable"]
        and not env["stylist"]["demo_mode"]
    ):
        missing_actions.append("Configure and start OpenClaw sidecar, then set STYLIST_OPENCLAW_CHAT_URL and STYLIST_OPENCLAW_MEMORY_URL.")
    if not env["stylist"]["model_key_present"]:
        accepted = ", ".join(env["stylist"]["accepted_model_key_env"]) or "a key matching STYLIST_OPENCLAW_MODEL"
        missing_actions.append(f"STYLIST_OPENCLAW_MODEL is {env['stylist']['model']}; add one of {accepted} to .env.")
    elif not env["stylist"]["model_key_matches_provider"]:
        accepted = ", ".join(env["stylist"]["accepted_model_key_env"]) or "a key matching STYLIST_OPENCLAW_MODEL"
        missing_actions.append(
            f"STYLIST_OPENCLAW_MODEL is {env['stylist']['model']}; add one of {accepted}, or change STYLIST_OPENCLAW_MODEL to match the configured provider key."
        )
    if not sidecars["xiaohongshu_mcp"]["source_present"]:
        missing_actions.append("Bootstrap Xiaohongshu MCP with selfit-agent-runtime/scripts/bootstrap-xhs-mcp.sh.")
    if not (
        sidecars["xiaohongshu_mcp"]["docker_available"]
        or sidecars["xiaohongshu_mcp"]["go_available"]
        or sidecars["xiaohongshu_mcp"]["vendored_go_available"]
    ):
        missing_actions.append("Install Docker/Go or run selfit-agent-runtime/scripts/bootstrap-go-runtime.py for the Xiaohongshu MCP sidecar.")
    if not ready["xhs_search"]:
        missing_actions.append("Start Xiaohongshu MCP sidecar and set SELFIT_XHS_MCP_URL.")
    if not ready["real_tryon"]:
        missing_actions.append("Fill try-on image generation provider keys in .env.")

    return {
        "status": "ready_for_full_user_trial" if all(ready.values()) else "missing_runtime_dependencies",
        "modules": modules,
        "env": env,
        "endpoints": endpoints,
        "sidecars": sidecars,
        "ready": ready,
        "missing_actions": missing_actions,
    }


def main() -> int:
    report = readiness()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if "--strict" in sys.argv and report["status"] != "ready_for_full_user_trial":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

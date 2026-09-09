"""Local, noninteractive Codex vision calls using the developer's CLI login."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading

from fastapi import HTTPException
from PIL import Image

from app.ops import deployment_mode, is_public_demo_mode

LOGGER = logging.getLogger(__name__)
_CALL_LOCK = threading.BoundedSemaphore(1)
_TIMEOUT_SECONDS = 120


def _binary() -> str:
    configured = os.getenv("SELFIT_CODEX_BIN", "").strip()
    path = shutil.which(configured or "codex")
    if not path and not configured:
        bundled = Path("/Applications/Codex.app/Contents/Resources/codex")
        if bundled.is_file() and os.access(bundled, os.X_OK):
            path = str(bundled)
    if not path:
        raise HTTPException(503, "本地搭配助手未就绪，请先安装并登录 Codex。")
    return path


def ask_json(image: Image.Image, prompt: str, schema: dict) -> dict:
    if deployment_mode() not in {"local", "dev", "development", "test"} or is_public_demo_mode():
        raise HTTPException(503, "当前环境无法使用本地搭配助手。")
    binary = _binary()
    if not _CALL_LOCK.acquire(blocking=False):
        raise HTTPException(429, "搭配助手正在处理另一件单品，请稍后再试。")
    try:
        with tempfile.TemporaryDirectory(prefix="selfit-codex-") as directory:
            root = Path(directory)
            photo, contract, output = root / "garment.png", root / "schema.json", root / "result.json"
            image.save(photo, format="PNG")
            contract.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            command = [binary, "--ask-for-approval", "never", "exec", "--ignore-user-config",
                       "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
                       "--color", "never", "--cd", directory,
                       "--image", str(photo), "--output-schema", str(contract),
                       "--output-last-message", str(output)]
            # This is a bounded visual judgment, with no repository or external tools.
            for feature in ("shell_tool", "apps", "plugins", "multi_agent", "hooks", "browser_use",
                            "browser_use_external", "computer_use", "image_generation", "skill_search"):
                command.extend(["--disable", feature])
            model = os.getenv("SELFIT_CODEX_MODEL", "").strip()
            if model:
                command.extend(["--model", model])
            command.append("-")
            with subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, text=True, start_new_session=True) as process:
                try:
                    process.communicate(
                        "只分析已附图片和下列资料，直接返回符合约定结构的 JSON。无需调用工具。\n" + prompt,
                        timeout=_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    # Kill the complete request group, including any CLI helper process.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    raise HTTPException(504, "这次搭配等待较久，请稍后重试。") from None
                if process.returncode:
                    LOGGER.warning("Local Codex request failed (exit %s)", process.returncode)
                    raise HTTPException(503, "本地搭配助手暂不可用，请检查 Codex 登录、网络或可用额度。")
            result = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(result, dict) or not result:
                raise ValueError("Empty Codex result")
            return result
    except HTTPException:
        raise
    except (OSError, ValueError) as exc:
        # Never forward CLI output or auth/config paths into consumer responses.
        LOGGER.warning("Local Codex request failed: %s", type(exc).__name__)
        raise HTTPException(502, "这次没有完成搭配，请再试一次。") from None
    finally:
        _CALL_LOCK.release()

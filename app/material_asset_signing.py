"""Operator-only signing for upload/refresh. Image readers never call this module."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path

DEFAULT_URL_TTL_SECONDS = 7 * 24 * 60 * 60


def sign_qiniu_url(source_url: str, *, ttl_seconds: int | None = None) -> tuple[str, int]:
    from dotenv import dotenv_values

    if ttl_seconds is None:
        ttl_seconds = int(os.getenv("QINIU_MATERIAL_URL_TTL_SECONDS", str(DEFAULT_URL_TTL_SECONDS)))
    if ttl_seconds <= 0:
        raise ValueError("Temporary URL lifetime must be positive")
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(Path(os.getenv("QINIU_ENV_FILE") or root / ".env.qiniu"))
    access_key = os.getenv("QINIU_ACCESS_KEY") or values.get("QINIU_ACCESS_KEY")
    secret_key = os.getenv("QINIU_SECRET_KEY") or values.get("QINIU_SECRET_KEY")
    if not access_key or not secret_key:
        raise ValueError("Qiniu signing credentials are required only to upload or refresh material URLs")
    expires_at = int(time.time()) + ttl_seconds
    unsigned = f"{source_url}{'&' if '?' in source_url else '?'}e={expires_at}"
    signature = base64.urlsafe_b64encode(hmac.new(secret_key.encode(), unsigned.encode(), hashlib.sha1).digest()).decode()
    return f"{unsigned}&token={access_key}:{signature}", expires_at

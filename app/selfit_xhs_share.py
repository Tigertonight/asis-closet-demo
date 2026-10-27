"""Server-only Xiaohongshu JS SDK signing; no publishing API is called."""
from __future__ import annotations

import fcntl
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.storage import ROOT_DIR

logger = logging.getLogger(__name__)
TOKEN_URL = "https://edith.xiaohongshu.com/api/sns/v1/ext/access/token"
CHECK_URL = "https://edith.xiaohongshu.com/api/sns/v1/ext/check/token"
REFRESH_MARGIN_MS = 120_000


class ShareUnavailable(Exception):
    pass


def configured():
    return bool(os.getenv("SELFIT_XHS_APP_KEY", "").strip() and os.getenv("SELFIT_XHS_APP_SECRET", "").strip())


def signature(app_key, nonce, timestamp, secret):
    # The official Java example sorts these three keys, then appends the secret
    # with no separator (not an appSecret= parameter). Both signatures use this.
    value = f"appKey={app_key}&nonce={nonce}&timeStamp={timestamp}{secret}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _directory():
    return Path(os.getenv("SELFIT_XHS_CACHE_DIR", str(ROOT_DIR / "outputs" / "xhs_share")))


@contextmanager
def _locked(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "token.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as lock:
        deadline = time.monotonic() + 12
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ShareUnavailable("分享准备中，请稍后重试。") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _save_cache(path, value):
    fd, name = tempfile.mkstemp(prefix=".token-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _request_token(app_key, app_secret):
    now = int(time.time() * 1000)
    nonce = secrets.token_hex(16)
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post(TOKEN_URL, json={
            "app_key": app_key, "nonce": nonce, "timestamp": now,
            "signature": signature(app_key, nonce, now, app_secret),
        })
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or payload
    if payload.get("success") is False or not isinstance(data, dict):
        raise ValueError("Token request rejected")
    token, expires = data.get("access_token"), data.get("expires_in")
    if not isinstance(token, str) or not token or not isinstance(expires, (int, float)) or expires <= now + REFRESH_MARGIN_MS:
        raise ValueError("Invalid token response")
    return token, int(expires)


def verify_config():
    app_key = os.getenv("SELFIT_XHS_APP_KEY", "").strip()
    app_secret = os.getenv("SELFIT_XHS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        raise ShareUnavailable("小红书分享暂未开放，可以先保存照片。")
    fingerprint = hashlib.sha256(f"{app_key}\0{app_secret}".encode()).hexdigest()
    directory = _directory()
    with _locked(directory):
        path = directory / "token.json"
        try:
            cache = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            cache = {}
        if not isinstance(cache, dict) or cache.get("credentialFingerprint") != fingerprint:
            cache = {}
        now = int(time.time() * 1000)
        if not cache.get("accessToken") or cache.get("expiresAt", 0) <= now + REFRESH_MARGIN_MS:
            if cache.get("retryAfter", 0) > now:
                raise ShareUnavailable("小红书分享暂时不可用，请稍后重试或先保存照片。")
            try:
                token, expires = _request_token(app_key, app_secret)
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                # Provider response bodies may contain credentials. Log only class/status.
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                logger.warning("xhs_token_unavailable type=%s status=%s", type(exc).__name__, status)
                _save_cache(path, {"credentialFingerprint": fingerprint, "retryAfter": now + 30_000})
                raise ShareUnavailable("小红书分享暂时不可用，请稍后重试或先保存照片。") from None
            cache = {"credentialFingerprint": fingerprint, "accessToken": token, "expiresAt": expires}
            _save_cache(path, cache)
    # Browser signatures expire before the cache's refresh boundary, because a
    # provider token refresh invalidates the previous token immediately.
    now = int(time.time() * 1000)
    nonce, timestamp = secrets.token_hex(16), str(now)
    return {"verifyConfig": {"appKey": app_key, "nonce": nonce, "timestamp": timestamp,
                             "signature": signature(app_key, nonce, timestamp, cache["accessToken"])},
            "expiresAt": min(now + 180_000, cache["expiresAt"] - REFRESH_MARGIN_MS)}


def _request_share_code(config, data):
    # Same wire protocol as official xhs-1.0.1.js. Prepare before the browser
    # tap so its platform sniffing / async fetch cannot swallow app activation.
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post(CHECK_URL, json={
            "app_key": config["appKey"], "nonce": config["nonce"],
            "timestamp": config["timestamp"], "signature": config["signature"],
            "data": base64.b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).decode(),
        })
    response.raise_for_status()
    result = response.json()
    code = (result.get("data") or {}).get("data_code")
    if result.get("success") is not True or not isinstance(code, str) or not 1 <= len(code) <= 4096:
        raise ValueError("Share preparation rejected")
    return code


def prepare_share(image_url, page_url, user_agent):
    result = verify_config()
    config = result["verifyConfig"]
    agent = (user_agent or "")[:1024]
    platform = "Android" if re.search("android", agent, re.I) else "iOS" if re.search("iphone|ipad|ipod", agent, re.I) else "pc"
    session_id = secrets.token_hex(5)
    share = {"type": "normal", "images": [image_url]}
    try:
        code = _request_share_code(config, {
            **share, "sessionId": session_id, "pageUrl": page_url,
            "appPlatform": platform, "userAgent": agent, "appKey": config["appKey"],
        })
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning("xhs_share_unavailable type=%s status=%s", type(exc).__name__, status)
        raise ShareUnavailable("小红书分享准备失败，请重试或先保存照片。") from None
    scheme = "xhsdiscover://js_share_sdk?" + urlencode({"share_code": code, "app_key": config["appKey"], "session_id": session_id})
    return {**result, "shareInfo": share, "launch": {
        "scheme": scheme, "universal": "https://oia.xiaohongshu.com/oia?" + urlencode({"deeplink": scheme}),
        "platform": platform, "inWeChat": bool(re.search("micromessenger", agent, re.I)),
    }}

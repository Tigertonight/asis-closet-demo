"""Small, structured request timing records without bodies, credentials or URLs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs

from app.ops import env_int

# Uvicorn already sends this logger to the service's runtime log.
logger = logging.getLogger("uvicorn.error")


class PrivatePhotoAccessLogFilter(logging.Filter):
    """Do not persist short-lived image capabilities in Uvicorn access logs."""
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2]
            if path.startswith("/api/v1/selfit/mirror/photos/"):
                record.args = (*args[:2], path.split("?", 1)[0], *args[3:])
        return True


def mirror_client_context(scope):
    """Untrusted correlation only; never use this browser ID for authentication."""
    header = dict(scope.get("headers", [])).get(b"x-selfit-client-id")
    if header is not None:
        if len(header) != 35:
            return {}
        value = header.decode("latin1")
        return {"client_id": value, "client_id_source": "header"} if re.fullmatch(r"mc_[a-f0-9]{32}", value) else {}
    # Native image fetches cannot carry custom headers. Carry the originating
    # browser's ID with the signed image; it does not identify the fetcher itself.
    query = scope.get("query_string", b"")
    if len(query) > 4096:
        return {}
    try:
        values = parse_qs(query.decode("ascii"), max_num_fields=16).get("client_id", [])
    except (ValueError, UnicodeDecodeError):
        return {}
    if len(values) == 1 and re.fullmatch(r"mc_[a-f0-9]{32}", values[0]):
        return {"client_id": values[0], "client_id_source": "photo_link"}
    return {}


def mirror_share_context(scope):
    """Bounded classifications only; never log raw UA, IP, URLs or credentials."""
    match = re.match(r"^/api/v1/selfit/mirror/photos/(mp_[a-f0-9]{32})(?:/|$)", scope.get("path", ""))
    if not match:
        return {}
    headers = dict(scope.get("headers", []))
    agent = headers.get(b"user-agent", b"")[:1024].decode("latin1").lower()
    platform = "ios" if re.search(r"iphone|ipad|ipod", agent) else "android" if "android" in agent else "other"
    family = "other"
    for name, pattern in [("xiaohongshu", r"xiaohongshu|xhsdiscover|discover/|redapp/"),
                          ("wechat", r"micromessenger"), ("apple_network", r"cfnetwork|urlsession"),
                          ("chrome", r"chrome|crios"), ("safari", r"safari")]:
        if re.search(pattern, agent):
            family = name
            break
    destination = headers.get(b"sec-fetch-dest", b"").decode("latin1")
    return {"photo_ref": hashlib.sha256(match[1].encode()).hexdigest()[:12],
            "client_platform": platform, "client_family": family,
            "fetch_destination": destination if destination in {"image", "document", "empty"} else "unknown",
            **mirror_client_context(scope)}


def _is_disconnect(exc):
    if isinstance(exc, asyncio.CancelledError) or type(exc).__name__ == "ClientDisconnect":
        return True
    children = getattr(exc, "exceptions", ())
    return bool(children) and all(_is_disconnect(child) for child in children)


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app
        access_logger = logging.getLogger("uvicorn.access")
        if not any(isinstance(f, PrivatePhotoAccessLogFilter) for f in access_logger.filters):
            access_logger.addFilter(PrivatePhotoAccessLogFilter())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        request_id = secrets.token_hex(12)
        scope.setdefault("state", {})["http_request_id"] = request_id
        status = None
        header_ms = None
        completed_ms = None
        response_bytes = 0
        disconnected = False
        error_type = None

        async def timed_receive():
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        async def timed_send(message):
            nonlocal status, header_ms, completed_ms, response_bytes
            if message["type"] == "http.response.start":
                status = message["status"]
                header_ms = (time.perf_counter() - started) * 1000
                # Never trust incoming request IDs or let them inject log fields.
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-request-id"]
                message = {**message, "headers": [*headers, (b"x-request-id", request_id.encode())]}
            await send(message)
            if message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
                if not message.get("more_body", False):
                    completed_ms = (time.perf_counter() - started) * 1000

        try:
            await self.app(scope, timed_receive, timed_send)
        except BaseException as exc:
            error_type = type(exc).__name__
            if _is_disconnect(exc):
                disconnected = True
            raise
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            duration = completed_ms if completed_ms is not None else elapsed
            route = scope.get("route")
            # Route templates redact session IDs, share tokens, filenames, etc.
            # Unmatched URLs are intentionally not logged (may contain secrets).
            path = getattr(route, "path", None)
            if path is None:
                path = "/static/{path}" if scope.get("path", "").startswith("/static/") else "/unmatched"
            outcome = "completed" if completed_ms is not None else "incomplete"
            if error_type:
                outcome = "disconnected" if disconnected else "error"
            elif disconnected and completed_ms is None:
                outcome = "disconnected"
            record = {
                "event": "http_request", "timestamp": timestamp,
                "request_id": request_id, "method": scope.get("method"),
                "route": path, "status": status if status is not None else (499 if disconnected else 500),
                "duration_ms": round(duration, 2),
                "headers_ms": round(header_ms, 2) if header_ms is not None else None,
                "handler_ms": round(elapsed, 2), "response_bytes": response_bytes,
                "outcome": outcome, "error_type": error_type,
                "slow": duration >= max(1, env_int("SELFIT_SLOW_REQUEST_MS", 1000)),
            }
            record.update(mirror_share_context(scope))
            flow = scope.get("state", {}).get("xhs_share_flow")
            if flow in {"official-sdk", "prepared-link"}:
                record["share_flow"] = flow
            level = logging.WARNING if record["slow"] or error_type or record["status"] >= 500 else logging.INFO
            logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":")))

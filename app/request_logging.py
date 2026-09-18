"""Small, structured request timing records without bodies, credentials or URLs."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone

from app.ops import env_int

# Uvicorn already sends this logger to the service's runtime log.
logger = logging.getLogger("uvicorn.error")


def _is_disconnect(exc):
    if isinstance(exc, asyncio.CancelledError) or type(exc).__name__ == "ClientDisconnect":
        return True
    children = getattr(exc, "exceptions", ())
    return bool(children) and all(_is_disconnect(child) for child in children)


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app

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
            level = logging.WARNING if record["slow"] or error_type or record["status"] >= 500 else logging.INFO
            logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":")))

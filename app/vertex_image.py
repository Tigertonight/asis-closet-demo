"""Google generateContent transport using server-side Application Default Credentials."""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any

MODE = "vertex_adc_generate_content"
DEFAULT_MODEL = "gemini-3.1-flash-image"
_state = threading.local()
_logger = logging.getLogger("uvicorn.error")


def _error_diagnostics(response) -> dict[str, Any]:
    """Extract bounded, structured diagnostics; never log raw bodies or messages."""
    fields: dict[str, Any] = {}
    headers = response.headers
    for header in ("x-request-id", "x-goog-request-id", "x-cloud-trace-context"):
        value = headers.get(header, "")
        if re.fullmatch(r"[a-zA-Z0-9;=/_-]{1,160}", value):
            fields[header.replace("-", "_")] = value
    retry = headers.get("Retry-After", "")
    if re.fullmatch(r"[0-9]{1,8}", retry):
        fields["retry_after_seconds"] = int(retry)
    # Authentication responses may contain credential details. Do not parse them.
    if response.status_code not in (429, 500, 502, 503, 504):
        return fields
    try:
        data = response.json()
    except (ValueError, TypeError):
        return fields
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return fields
    status = error.get("status")
    if isinstance(status, str) and status in {"RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED"}:
        fields["upstream_status"] = status
    message = error.get("message", "")
    if isinstance(message, str):
        message = message.lower()
        # Classifications are evidence from wording, not a guessed root cause.
        for phrase, category in (
            ("exceeded the provisioned throughput", "provisioned_throughput_exceeded"),
            ("quota exceeded", "quota_exceeded"),
            ("resource exhausted", "resource_exhausted_unspecified"),
            ("too many requests", "too_many_requests"),
        ):
            if phrase in message:
                fields["message_category"] = category
                break
    details = error.get("details", [])
    if not isinstance(details, list):
        return fields
    for detail in details[:10]:
        if not isinstance(detail, dict):
            continue
        kind = detail.get("@type")
        if kind == "type.googleapis.com/google.rpc.QuotaFailure":
            fields["quota_failure"] = True
        elif kind == "type.googleapis.com/google.rpc.RetryInfo":
            delay = detail.get("retryDelay")
            if isinstance(delay, str) and re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,9})?s", delay):
                fields["retry_delay"] = delay
        elif kind == "type.googleapis.com/google.rpc.ErrorInfo":
            reason = detail.get("reason")
            if isinstance(reason, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", reason):
                fields["error_reason"] = reason
            metadata = detail.get("metadata", {})
            if isinstance(metadata, dict):
                for key in ("quota_metric", "quota_limit"):
                    value = metadata.get(key)
                    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9._/-]{1,200}", value) and "projects/" not in value:
                        fields[key] = value
    return fields


def _log_request(start: float, call_id: str, **fields: Any) -> None:
    event = {"event": "vertex_generate_content", "call_id": call_id,
             "timestamp": datetime.now(timezone.utc).isoformat(),
             "model": model(), "location": os.getenv("TRYON_VERTEX_LOCATION", "global"),
             "duration_ms": round((time.monotonic() - start) * 1000), **fields}
    _logger.log(logging.WARNING if fields.get("outcome") != "success" else logging.INFO,
                json.dumps(event, ensure_ascii=True, separators=(",", ":")))


def enabled() -> bool:
    return os.getenv("TRYON_GOOGLE_BACKEND", "").strip().lower() == "vertex_adc"


def model() -> str:
    return os.getenv("TRYON_IMAGE_MODEL", "").strip() or DEFAULT_MODEL


def project() -> str:
    return os.getenv("TRYON_VERTEX_PROJECT", "").strip() or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()


def endpoint() -> str:
    location = os.getenv("TRYON_VERTEX_LOCATION", "global").strip()
    if not all(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", part) for part in (project(), location, model())):
        raise ValueError("Vertex project, location and model must be configured as resource IDs")
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{project()}/locations/{location}/publishers/google/models/{model()}:generateContent"


def _credentials():
    # Each worker owns its credentials; no shared Session or concurrent token mutation.
    path = Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
                str(Path(os.getenv("CLOUDSDK_CONFIG") or Path.home() / ".config/gcloud") / "application_default_credentials.json"))
    stat = path.stat()
    signature = (str(path), stat.st_mtime_ns, stat.st_size, project())
    if getattr(_state, "signature", None) != signature:
        import google.auth

        credentials, _ = google.auth.load_credentials_from_file(
            str(path), scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id=project(),
        )
        _state.credentials = credentials
        _state.signature = signature
    return _state.credentials


def configured() -> bool:
    """Configuration check only: never refresh credentials or generate an image."""
    if not enabled():
        return False
    try:
        endpoint()
        _credentials()
        return True
    except Exception:
        return False


def generate_content(payload: dict[str, Any], *, timeout: float = 180) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError("Vertex ADC backend is not enabled")
    start, call_id = time.monotonic(), uuid.uuid4().hex
    logged = False
    try:
        from google.auth.transport.requests import AuthorizedSession, Request
        import requests

        url = endpoint()
        credentials = _credentials()
        # Keep OAuth and model traffic direct. AuthorizedSession refreshes expired
        # tokens and retries authentication failures, but not billed 429/5xx calls.
        with requests.Session() as auth_session:
            auth_session.trust_env = False
            with AuthorizedSession(credentials, auth_request=Request(session=auth_session), refresh_timeout=20) as session:
                session.trust_env = False
                response = session.post(url, json=payload, timeout=(20, timeout), allow_redirects=False)
        if response.status_code != 200:
            _log_request(start, call_id, outcome="http_error", http_status=response.status_code,
                         **_error_diagnostics(response))
            logged = True
            raise RuntimeError(f"Vertex generateContent HTTP {response.status_code}")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Vertex returned an invalid response")
        _log_request(start, call_id, outcome="success", http_status=200)
        return data
    except Exception as exc:
        if not logged:
            _log_request(start, call_id, outcome="request_error", error_type=type(exc).__name__)
        # OAuth error bodies can carry credential details. Never return raw errors
        # or request headers to API clients, job manifests, or application logs.
        if isinstance(exc, RuntimeError) and str(exc).startswith("Vertex "):
            raise RuntimeError(str(exc)) from None
        raise RuntimeError(f"Vertex ADC request failed ({type(exc).__name__})") from None

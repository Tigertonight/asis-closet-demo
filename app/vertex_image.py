"""Google generateContent transport using server-side Application Default Credentials."""
from __future__ import annotations

import os
from pathlib import Path
import re
import threading
from typing import Any

MODE = "vertex_adc_generate_content"
DEFAULT_MODEL = "gemini-3.1-flash-image"
_state = threading.local()


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
            raise RuntimeError(f"Vertex generateContent HTTP {response.status_code}")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Vertex returned an invalid response")
        return data
    except Exception as exc:
        # OAuth error bodies can carry credential details. Never return raw errors
        # or request headers to API clients, job manifests, or application logs.
        if isinstance(exc, RuntimeError) and str(exc).startswith("Vertex "):
            raise RuntimeError(str(exc)) from None
        raise RuntimeError(f"Vertex ADC request failed ({type(exc).__name__})") from None

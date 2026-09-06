"""Collect PERF-001 HTTP samples in an isolated loopback test environment.

Credentials come from environment variables named in the account configuration.
This creates recommendation session snapshots, but never changes profiles,
feedback, content or release flags. The raw result requires QA environment and
runtime-source verification before it can become formal acceptance evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_anchors import PERSONAS


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward credentials to a redirect target.


def p95(samples):
    if not samples or any(not math.isfinite(v) or v < 0 for v in samples):
        raise ValueError("Samples must be finite nonnegative durations")
    return sorted(samples)[math.ceil(.95 * len(samples)) - 1]


def http_json(base_url, path, token=None, payload=None, timeout=10):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = Request(base_url + path, data=data, headers=headers)
    started = time.perf_counter()
    status, raw, error = None, b"", None
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except HTTPError as exc:
        status = exc.code
        exc.close()
        error = "http_error"
    except (URLError, OSError, TimeoutError):
        error = "transport_error"
    elapsed = (time.perf_counter() - started) * 1000
    # End timing after receiving all response bytes, before JSON validation.
    try:
        body = json.loads(raw) if error is None else None
        if not isinstance(body, dict):
            error = error or "invalid_json_object"
    except (ValueError, UnicodeError):
        body, error = None, "invalid_json"
    return {"elapsed_ms": elapsed, "http_status": status, "error": error,
            "body": body, "response_sha256": hashlib.sha256(raw).hexdigest() if raw else None}


def load_accounts(path):
    rows = json.loads(path.read_bytes())
    if (not isinstance(rows, list) or len(rows) != 16
            or any(not isinstance(row, dict) or not isinstance(row.get("persona"), str)
                   for row in rows)
            or {row["persona"] for row in rows} != PERSONAS):
        raise ValueError("Account configuration must contain each of the 16 personas exactly once")
    accounts = []
    for row in sorted(rows, key=lambda r: r["persona"]):
        variable = row.get("token_env")
        if not isinstance(variable, str) or not re.fullmatch(r"P0_TOKEN_[A-Z0-9_]+", variable):
            raise ValueError("Each credential must reference a P0_TOKEN_* environment variable")
        token = os.environ.get(variable, "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("A required test-account credential is missing or malformed")
        accounts.append({"persona": row["persona"], "token": token})
    if len({a["token"] for a in accounts}) != 16:
        raise ValueError("The 16 formal personas require distinct account credentials")
    return accounts


def response_errors(sample, persona, profile_version, manifest_sha, blind_sha, anchor_ids):
    if sample["error"] or sample["http_status"] != 200:
        return [sample["error"] or "http_error"]
    body = sample["body"]
    errors = []
    release = body.get("anchor_release")
    if (not isinstance(release, dict) or release.get("valid") is not True
            or release.get("manifest_sha256") != manifest_sha
            or release.get("blind_result_sha256") != blind_sha):
        errors.append("p0_release_missing_or_changed")
    if body.get("profile_version") != profile_version or body.get("profile_required"):
        errors.append("profile_missing_or_changed")
    carousel, feed = body.get("carousel"), body.get("outfits")
    if not isinstance(carousel, list) or not isinstance(feed, list):
        return errors + ["invalid_feed_shape"]
    rows = carousel + feed
    if any(not isinstance(row, dict) for row in rows):
        return errors + ["invalid_feed_row"]
    ids = [row.get("outfit_id") for row in rows]
    if (len(carousel) != 4 or len(feed) != 6 or any(not isinstance(oid, str) for oid in ids)
            or len(set(str(oid) for oid in ids)) != 10):
        errors.append("first_ten_missing_or_duplicated")
    if any(not isinstance(oid, str) or oid not in anchor_ids for oid in ids):
        errors.append("non_anchor_content")
    if any(str(row.get("primary_persona") or "").lower() != persona for row in rows):
        errors.append("unexpected_persona")
    return errors


def measure(base_url, accounts, manifest_sha, blind_sha, anchor_ids, expected_release,
            request=http_json):
    started_at = datetime.now(timezone.utc).isoformat()
    health_before = request(base_url, "/health")
    preflight_errors, versions = [], {}
    if (health_before["error"] or health_before["http_status"] != 200
            or (health_before["body"] or {}).get("release") != expected_release):
        preflight_errors.append("health_release_mismatch")
    for account in accounts:
        sample = request(base_url, "/closet/recommendations/profile", account["token"])
        body = sample["body"] or {}
        if (sample["error"] or sample["http_status"] != 200
                or body.get("persona_id") != account["persona"] or not body.get("version")):
            preflight_errors.append(account["persona"] + ": formal profile unavailable or mismatched")
        else:
            versions[account["persona"]] = body["version"]
    result = {"schema_version": 1, "started_at": started_at, "base_url": base_url,
              "anchor_manifest_sha256": manifest_sha, "blind_result_sha256": blind_sha,
              "expected_health_release": expected_release,
              "measurement_scope": "complete_serial_HTTP_response_not_browser_or_load_test",
              "formal_acceptance": False, "cases": {"PERF-001": "Not Run"},
              "preflight_errors": preflight_errors, "warmup": [], "samples": []}
    if preflight_errors:
        result["status"] = "blocked_preconditions"
        return result
    for phase, count in (("warmup", 5), ("samples", 50)):
        for index in range(count):
            account = accounts[index % len(accounts)]
            # Formal identity comes from the authenticated account, never a
            # persona_preview payload. Each sample is a fresh first-page request.
            sample = request(base_url, "/closet/recommendations/outfits", account["token"], {})
            errors = response_errors(sample, account["persona"], versions[account["persona"]],
                                     manifest_sha, blind_sha, anchor_ids)
            # Never persist tokens, raw profiles, response bodies or exception strings.
            result[phase].append({"index": index + 1, "persona": account["persona"],
                "elapsed_ms": sample["elapsed_ms"], "http_status": sample["http_status"],
                "response_sha256": sample["response_sha256"], "errors": errors})
    health_after = request(base_url, "/health")
    if (health_after["error"] or health_after["http_status"] != 200
            or (health_after["body"] or {}).get("release") != expected_release):
        result["preflight_errors"].append("health_release_changed_or_unavailable_after_run")
    samples = result["samples"]
    failures = sum(bool(s["errors"]) for s in samples)
    result.update(p95_ms=p95([s["elapsed_ms"] for s in samples]),
                  error_rate=failures / 50, failed_samples=failures,
                  distribution=dict(Counter(s["persona"] for s in samples)),
                  finished_at=datetime.now(timezone.utc).isoformat())
    result["status"] = ("measurement_threshold_pass" if result["p95_ms"] <= 1000 and not failures
                        and not any(s["errors"] for s in result["warmup"])
                        and not result["preflight_errors"] else "measurement_threshold_fail")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Explicit isolated loopback server, including port")
    parser.add_argument("--accounts", type=Path, required=True, help="16 persona/token_env records; no inline secrets")
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--blind-result", type=Path, required=True)
    parser.add_argument("--expected-release", required=True, help="Expected /health release string")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (url.scheme not in {"http", "https"} or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}
            or not url.port):
        raise ValueError("Use an explicit loopback origin with a port; remote runs are not supported")
    if args.output.exists():
        raise ValueError("Refusing to overwrite performance evidence")
    anchor_bytes, blind_bytes = args.anchor_manifest.read_bytes(), args.blind_result.read_bytes()
    manifest = json.loads(anchor_bytes)
    rows = manifest.get("anchors") or []
    ids = [row.get("outfit_id") for row in rows if isinstance(row, dict)]
    if (len(rows) != 160 or len(ids) != 160 or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != 160):
        raise ValueError("Performance acceptance requires 160 distinct anchor IDs")
    result = measure(args.base_url.rstrip("/"), load_accounts(args.accounts),
                     hashlib.sha256(anchor_bytes).hexdigest(), hashlib.sha256(blind_bytes).hexdigest(),
                     set(ids), args.expected_release)
    if args.anchor_manifest.read_bytes() != anchor_bytes or args.blind_result.read_bytes() != blind_bytes:
        result["preflight_errors"].append("evidence_inputs_changed_during_run")
        result["status"] = "measurement_threshold_fail"
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "samples": len(result["samples"]),
                      "p95_ms": result.get("p95_ms"), "formal_acceptance": False}))
    return 0 if result["status"] == "measurement_threshold_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

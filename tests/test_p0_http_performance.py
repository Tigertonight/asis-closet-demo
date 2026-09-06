import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("p0_http_measure", Path(__file__).resolve().parents[1]
                                            / "scripts/measure_selfit_p0_http.py")
measure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure)


def response(body, elapsed=200, status=200, error=None):
    return {"body": body, "elapsed_ms": elapsed, "http_status": status,
            "error": error, "response_sha256": "response-digest"}


@pytest.fixture
def harness():
    accounts = [{"persona": p, "token": "secret-" + p} for p in sorted(measure.PERSONAS)]
    ids = {f"{p}-{n}" for p in measure.PERSONAS for n in range(10)}
    calls = []
    def request(base, path, token=None, payload=None):
        calls.append((path, token, payload))
        if path == "/health":
            return response({"release": "test-release"})
        persona = token.removeprefix("secret-")
        if path.endswith("profile"):
            return response({"persona_id": persona, "version": persona + "-version"})
        rows = [{"outfit_id": f"{persona}-{n}", "primary_persona": persona.upper()} for n in range(10)]
        return response({"carousel": rows[:4], "outfits": rows[4:],
                         "profile_version": persona + "-version",
                         "anchor_release": {"valid": True, "manifest_sha256": "anchors",
                                            "blind_result_sha256": "blind"}})
    def run(transport=request):
        return measure.measure("http://127.0.0.1:8999", accounts, "anchors", "blind", ids,
                               "test-release", request=transport)
    return run, request, calls


def test_exact_sampling_distribution_and_no_fake_formal_pass(harness):
    run, _, calls = harness
    result = run()
    assert result["status"] == "measurement_threshold_pass"
    assert len(result["warmup"]) == 5 and len(result["samples"]) == 50
    assert len(result["distribution"]) == 16
    assert sorted(result["distribution"].values()) == [3] * 14 + [4] * 2
    assert len(calls) == 73  # 2 health + 16 profiles + 5 warmup + 50 measured
    assert all(payload == {} for path, _, payload in calls if path.endswith("outfits"))
    assert result["cases"] == {"PERF-001": "Not Run"}
    assert not result["formal_acceptance"]
    assert "secret-" not in json.dumps(result)


@pytest.mark.parametrize("count, expected", [(20, 19), (50, 48)])
def test_nearest_rank_not_average(count, expected):
    assert measure.p95(list(range(count, 0, -1))) == expected


@pytest.mark.parametrize("samples", [[], [float("nan")], [float("inf")], [-1]])
def test_invalid_timings_rejected(samples):
    with pytest.raises(ValueError):
        measure.p95(samples)


@pytest.mark.parametrize("fault", ["empty_pool", "legacy", "stale_release", "wrong_persona", "wrong_profile", "http_error"])
def test_fast_invalid_responses_do_not_pass(harness, fault):
    run, request, _ = harness
    def broken(*args):
        sample = request(*args)
        if args[1].endswith("outfits"):
            body = sample["body"]
            if fault == "empty_pool":
                body["carousel"], body["outfits"] = [], []
            elif fault == "legacy":
                del body["anchor_release"]
            elif fault == "stale_release":
                body["anchor_release"]["manifest_sha256"] = "old"
            elif fault == "wrong_persona":
                body["outfits"][0]["primary_persona"] = "wrong"
            elif fault == "wrong_profile":
                body["profile_version"] = "changed"
            else:
                sample.update(http_status=503, error="http_error", body=None)
        return sample
    result = run(broken)
    assert result["status"] == "measurement_threshold_fail"
    assert result["failed_samples"] == 50
    assert result["error_rate"] == 1
    assert len(result["samples"]) == 50  # Do not drop failing or slow responses.


def test_bad_profile_prevents_sampling(harness):
    run, request, calls = harness
    def wrong(*args):
        sample = request(*args)
        if args[1].endswith("profile"):
            sample["body"]["persona_id"] = "wrong"
        return sample
    assert run(wrong)["status"] == "blocked_preconditions"
    assert not any(path.endswith("outfits") for path, _, _ in calls)


def test_release_changes_after_samples_are_retained_as_failure(harness):
    run, request, calls = harness
    def changed(*args):
        sample = request(*args)
        if args[1] == "/health" and len(calls) > 1:
            sample["body"]["release"] = "new-release"
        return sample
    result = run(changed)
    assert result["status"] == "measurement_threshold_fail"
    assert len(result["samples"]) == 50


def test_one_slow_failure_is_kept_even_when_p95_meets_target(harness):
    run, request, _ = harness
    count = 0
    def slow(*args):
        nonlocal count
        sample = request(*args)
        if args[1].endswith("outfits"):
            count += 1
            if count == 55:
                sample.update(elapsed_ms=10000, http_status=None, error="transport_error", body=None)
        return sample
    result = run(slow)
    assert result["p95_ms"] == 200
    assert result["samples"][-1]["elapsed_ms"] == 10000
    assert result["error_rate"] == .02
    assert result["status"] == "measurement_threshold_fail"


@pytest.mark.parametrize("elapsed, expected", [(1000, "measurement_threshold_pass"),
                                                (1000.01, "measurement_threshold_fail")])
def test_latency_threshold_boundary(harness, elapsed, expected):
    run, request, _ = harness
    def timed(*args):
        sample = request(*args)
        sample["elapsed_ms"] = elapsed
        return sample
    result = run(timed)
    assert result["p95_ms"] == elapsed
    assert result["error_rate"] == 0
    assert result["status"] == expected


def test_warmup_failure_cannot_be_hidden_by_fifty_successes(harness):
    run, request, _ = harness
    count = 0
    def failing_warmup(*args):
        nonlocal count
        sample = request(*args)
        if args[1].endswith("outfits"):
            count += 1
            if count == 1:
                sample.update(error="http_error", http_status=503, body=None)
        return sample
    result = run(failing_warmup)
    assert result["failed_samples"] == 0
    assert len(result["warmup"]) == 5
    assert result["warmup"][0]["errors"]
    assert result["status"] == "measurement_threshold_fail"


def test_actual_http_transport_reads_body_and_never_follows_redirect():
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            paths.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/secret-target")
                self.end_headers()
                return
            raw = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        result = measure.http_json(base, "/ok", "do-not-log")
        assert result["body"] == {"ok": True} and result["error"] is None
        assert result["elapsed_ms"] >= 0
        result = measure.http_json(base, "/redirect", "do-not-log")
        assert result["http_status"] == 302 and result["error"] == "http_error"
        assert paths == ["/ok", "/redirect"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_credentials_only_from_environment_and_distinct(tmp_path, monkeypatch):
    rows = [{"persona": p, "token_env": "P0_TOKEN_" + p.upper()} for p in sorted(measure.PERSONAS)]
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps(rows))
    for row in rows:
        monkeypatch.setenv(row["token_env"], "secret-" + row["persona"])
    assert len(measure.load_accounts(path)) == 16
    for row in rows:
        monkeypatch.setenv(row["token_env"], "same-secret")
    with pytest.raises(ValueError, match="distinct"):
        measure.load_accounts(path)
    path.write_text(json.dumps(rows[:15]))
    with pytest.raises(ValueError, match="16 personas"):
        measure.load_accounts(path)

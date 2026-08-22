from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.selfit_onboarding as selfit_onboarding
import app.selfit_onboarding_store as store_module
import app.selfit_report as selfit_report
from app.main import app

API = "/api/v1/selfit"


def _use_sqlite_store(monkeypatch, tmp_path: Path) -> Path:
    store_dir = tmp_path / "outputs" / "selfit_onboarding"
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_DIR", store_dir)
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_STORE_PATH", store_dir / "sessions.json")
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_ASSET_DIR", store_dir / "assets")
    monkeypatch.setenv("SELFIT_ONBOARDING_STORE_BACKEND", "sqlite")
    return store_dir


def test_sqlite_store_round_trip(tmp_path: Path) -> None:
    store = store_module.SqliteOnboardingStore(tmp_path / "sessions.sqlite3")
    assert store.load() == store_module.empty_store()

    data = store_module.empty_store()
    data["sessions"].append({"session_id": "ses_1", "status": "draft", "revision": 1})
    data["idempotency"].append({"key": "u:k1", "status_code": 201, "body": {"a": 1}, "created_at": "2026-08-22T00:00:00Z"})
    store.save(data)

    loaded = store.load()
    assert loaded["sessions"][0]["session_id"] == "ses_1"
    assert loaded["idempotency"][0]["body"] == {"a": 1}

    # 更新 + 删除语义：不在 save 载荷里的文档被移除
    loaded["sessions"][0]["revision"] = 2
    loaded["idempotency"] = []
    store.save(loaded)
    reloaded = store.load()
    assert reloaded["sessions"][0]["revision"] == 2
    assert reloaded["idempotency"] == []


def test_sqlite_store_ignores_corrupt_rows(tmp_path: Path) -> None:
    path = tmp_path / "sessions.sqlite3"
    store = store_module.SqliteOnboardingStore(path)
    store.save({**store_module.empty_store(), "sessions": [{"session_id": "ses_ok", "revision": 1}]})
    import sqlite3

    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO documents (collection, doc_id, doc) VALUES (?, ?, ?)",
            ("sessions", "ses_broken", "{not json"),
        )
    loaded = store.load()
    assert [item["session_id"] for item in loaded["sessions"]] == ["ses_ok"]


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 180, 170)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_sqlite_backend_full_api_flow(monkeypatch, tmp_path: Path) -> None:
    store_dir = _use_sqlite_store(monkeypatch, tmp_path)
    monkeypatch.setattr(selfit_onboarding, "REPORT_TOTAL_MS", -1)
    monkeypatch.setattr(selfit_report, "_builder", lambda session: {"title": "中性利落派"})
    client = TestClient(app)

    created = client.post(f"{API}/sessions", json={}, headers={"X-Idempotency-Key": "s1"})
    assert created.status_code == 201
    session_id = created.json()["session"]["sessionId"]

    replayed = client.post(f"{API}/sessions", json={}, headers={"X-Idempotency-Key": "s1"})
    assert replayed.json()["session"]["sessionId"] == session_id

    patched = client.patch(f"{API}/sessions/{session_id}/profile", json={"manual": {"skin": "自然白"}})
    assert patched.json()["session"]["revision"] == 2

    photo = client.post(f"{API}/sessions/{session_id}/photos/face", files={"image": ("a.jpg", _jpeg_bytes())})
    assert photo.json()["photo"]["status"] == "accepted"

    job = client.post(f"{API}/sessions/{session_id}/report-jobs", json={}).json()["job"]
    finished = client.get(f"{API}/report-jobs/{job['jobId']}").json()["job"]
    assert finished["status"] == "completed"
    report = client.get(f"{API}/reports/{finished['reportId']}").json()["report"]
    assert report["title"] == "中性利落派"

    share = client.post(
        f"{API}/reports/{finished['reportId']}/share-assets",
        json={"slideIndex": 0, "channel": "保存单张", "format": "png"},
    ).json()["asset"]
    download = client.get(share["downloadUrl"])
    assert download.status_code == 200

    # 数据确实落在 sqlite，且 json 文件未被创建
    assert (store_dir / "sessions.sqlite3").exists()
    assert not (store_dir / "sessions.json").exists()

    # 重启后（新连接）数据仍在
    assert client.get(f"{API}/sessions/{session_id}").json()["session"]["revision"] == 3

import json

from fastapi.testclient import TestClient

from app import auth, storage
from app.main import app


def test_native_history_reads_existing_records_for_the_signed_in_account(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setenv("SELFIT_PUBLIC_DEMO", "1")
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "history-test-only")
    endpoint = "/selfit/try-on/records"
    with TestClient(app, follow_redirects=False) as client:
        assert client.get(endpoint).status_code == 401
        owner = client.post("/auth/guest", json={}).json()
        other = client.post("/auth/guest", json={}).json()
        manifest = storage.storage_context(owner["user"]["user_id"]).tryon_records_manifest_path
        manifest.parent.mkdir(parents=True, exist_ok=True)
        older = {"record_id": "first", "created_at": "2026-01-01T09:00:00Z",
                 "outfit_title": "搭配一", "image_path": "/user-assets/tryon/first.png"}
        newer = dict(older, record_id="second", created_at="2026-01-02T09:00:00Z")
        removed = dict(older, record_id="removed", deleted=True)
        manifest.write_text(json.dumps({"version": 1, "records": [older, removed, newer]}))

        def history(account):
            response = client.get(endpoint, headers={"Authorization": "Bearer " + account["access_token"]})
            assert response.status_code == 200
            return response.json()

        assert history(owner) == {"total": 2, "records": [newer, older]}
        assert history(other) == {"total": 0, "records": []}

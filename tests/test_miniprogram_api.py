"""Native client routes must work with the public page gateway enabled."""
import secrets

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import auth, closet, storage
from app.main import app


@pytest.mark.parametrize("path", [
    "/api/v1/selfit/sessions/{session_id}/gender",
    "/api/v1/selfit/sessions/{session_id}/profile",
    "/api/v1/selfit/sessions/{session_id}/preferences",
    "/api/v1/selfit/sessions/{session_id}/vibe",
    "/api/v1/selfit/me/gender",
    "/api/v1/selfit/me/profile",
    "/selfit/try-on/inspiration-notes/{note_id}/favorite",
    "/closet/outfits/{outfit_id}",
])
def test_native_updates_use_the_website_handler(path):
    routes = {(route.path, method): route.endpoint for route in app.routes
              if isinstance(route, APIRoute) for method in route.methods}
    assert routes[(path + "/update", "POST")] is routes[(path, "PATCH")]


def test_native_studio_reads_use_the_signed_in_account(monkeypatch, tmp_path):
    monkeypatch.setenv("SELFIT_ENV", "production")
    monkeypatch.setenv("SELFIT_AUTH_SECRET", secrets.token_urlsafe(32))
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "auth" / "accounts.json")
    with TestClient(app, follow_redirects=False) as client:
        preferences = "/selfit/try-on/preferences"
        history = "/selfit/try-on/records"
        assert client.get(preferences).status_code == 401
        assert client.get(history).status_code == 401
        first, second = [client.post("/auth/guest").raise_for_status().json() for _ in range(2)]
        assert first["user"]["user_id"] != second["user"]["user_id"]
        first_headers = {"Authorization": "Bearer " + first["access_token"]}
        second_headers = {"Authorization": "Bearer " + second["access_token"]}
        with storage.user_storage(first["user"]["user_id"]):
            closet.update_user_preferences({"current_model_id": "self"})
            closet._write_tryon_records_manifest({"records": [{"record_id": "first-outfit"}]})
        assert client.get(preferences, headers=first_headers).json()["current_model_id"] == "self"
        assert client.get(preferences, headers=second_headers).json()["current_model_id"] != "self"
        assert [record["record_id"] for record in client.get(history, headers=first_headers).json()["records"]] == ["first-outfit"]
        assert client.get(history, headers=second_headers).json()["records"] == []
        wardrobe = client.get("/selfit/try-on/wardrobe", headers=first_headers).raise_for_status().json()
        item_id = wardrobe["items"][0]["item_id"]
        outfit = client.post("/selfit/try-on/outfits", headers=first_headers,
                             json={"item_ids": [item_id], "title": "Only mine"}).raise_for_status().json()
        path = "/selfit/try-on/outfits/" + outfit["outfit_id"]
        assert client.get(path).status_code == 401
        assert client.get(path, headers=second_headers).status_code == 404
        assert client.get(path, headers=first_headers).raise_for_status().json()["item_ids"] == [item_id]

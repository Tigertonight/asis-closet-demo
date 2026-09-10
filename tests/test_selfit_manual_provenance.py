from datetime import timedelta

import inspect
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import selfit_onboarding as onboarding
from app.selfit_suit import suit_summary

USER = {"user_id": "manual-provenance-test"}
FIELDS = ("skin", "faceShape", "bodyShape")
CHOICES = {"skin": "冷白肤", "faceShape": "方脸", "bodyShape": "梨型"}


def photo_session():
    return {
        "session_id": "ses_provenance", "user_id": USER["user_id"], "status": "draft", "revision": 1,
        "created_at": onboarding._iso(onboarding._now()),
        "expires_at": onboarding._iso(onboarding._now() + timedelta(hours=24)),
        "manual": {}, "preferences": {}, "vibe": {},
        "photos": {
            "face": {"asset_id": "test_face", "status": "accepted", "attributes": {
                "skin_tone": {"label": "暖黄肤", "confidence": 0.9},
                "face_shape": {"label": "椭圆脸", "confidence": 0.9},
            }},
            "body": {"asset_id": "test_body", "status": "accepted", "attributes": {
                "body_shape": {"label": "矩型", "confidence": 0.9},
            }},
        },
    }


def make_data(session, profile):
    data = onboarding._store_module.empty_store()
    data["sessions"].append(session)
    data["reports"].append({"report_id": "rep_provenance", "session_id": session["session_id"],
                            "user_id": USER["user_id"], "created_at": session["created_at"],
                            "data": {"typeId": "loop"}, "profile": profile})
    for kind in ("face", "body"):
        onboarding._index_user_photo(data, session, kind)
    return data


def sources(summary):
    return {feature["key"]: feature["source"] for feature in summary["features"]}


def test_legacy_automatic_report_snapshot_is_not_manual(photo_session):
    legacy = {"manual": onboarding._profile_manual(photo_session), "revision": 1}
    data = make_data(photo_session, legacy)
    profile = onboarding._account_profile(data, USER["user_id"])
    assert sources(profile["suit"]) == dict.fromkeys(FIELDS, "photo")
    assert profile["manualOverrides"] == {}


def test_only_explicit_choice_is_manual_in_session_and_report(photo_session, field):
    photo_session["manual"] = {field: CHOICES[field]}
    snapshot = onboarding._profile_snapshot(photo_session)
    assert snapshot["manualOverrides"] == {field: CHOICES[field]}
    data = make_data(photo_session, snapshot)
    expected = {key: "manual" if key == field else "photo" for key in FIELDS}
    assert sources(suit_summary(photo_session)) == expected
    assert sources(onboarding._account_profile(data, USER["user_id"])["suit"]) == expected
    # Provenance remains available after the source draft expires.
    data["sessions"] = []
    assert sources(onboarding._account_profile(data, USER["user_id"])["suit"]) == expected


def test_explicitly_reselecting_photo_value_still_counts(photo_session):
    photo_session["manual"] = {"skin": "暖黄肤"}
    data = make_data(photo_session, onboarding._profile_snapshot(photo_session))
    assert sources(onboarding._account_profile(data, USER["user_id"])["suit"])["skin"] == "manual"


def test_legacy_confirmed_profile_edit_is_preserved(photo_session):
    legacy = {"manual": {**onboarding._profile_manual(photo_session), "skin": "冷白肤"}, "revision": 2}
    data = make_data(photo_session, legacy)
    assert sources(onboarding._account_profile(data, USER["user_id"])["suit"]) == {"skin": "manual", "faceShape": "photo", "bodyShape": "photo"}


def test_accepted_replacement_clears_only_corresponding_manual_fields(photo_session, kind, cleared):
    photo_session["manual"] = CHOICES.copy()
    data = make_data(photo_session, onboarding._profile_snapshot(photo_session))
    onboarding._clear_manual_for_photo(data, USER["user_id"], kind)
    profile = onboarding._account_profile(data, USER["user_id"])
    assert sources(profile["suit"]) == {key: "photo" if key in cleared else "manual" for key in FIELDS}
    assert all(key not in profile["manualOverrides"] for key in cleared)


@contextmanager
def isolated_client():
    with tempfile.TemporaryDirectory(prefix="selfit-provenance-") as temporary:
        tmp_path = Path(temporary)
        with patch.dict(os.environ, {"SELFIT_ONBOARDING_STORE_BACKEND": "json"}), patch.multiple(
            onboarding, SELFIT_ONBOARDING_DIR=tmp_path,
            SELFIT_ONBOARDING_STORE_PATH=tmp_path / "sessions.json"
        ):
            app = FastAPI()
            app.include_router(onboarding.router)
            app.dependency_overrides[onboarding.get_optional_user] = lambda: USER
            app.dependency_overrides[onboarding.get_current_user] = lambda: USER
            with TestClient(app) as test_client:
                yield test_client


def test_session_api_marks_only_saved_field_and_new_session_starts_clean(client, photo_session, field):
    data = make_data(photo_session, {"manual": {}, "revision": 1})
    onboarding._write_store(data)
    url = f"/api/v1/selfit/sessions/{photo_session['session_id']}"
    assert sources(client.get(url + "/suit").json()) == dict.fromkeys(FIELDS, "photo")
    saved = client.patch(url + "/profile", json={"manual": {field: CHOICES[field]}})
    assert saved.status_code == 200
    assert sources(client.get(url + "/suit").json()) == {key: "manual" if key == field else "photo" for key in FIELDS}
    fresh = client.post("/api/v1/selfit/sessions", json={}).json()["session"]
    assert fresh["sessionId"] != photo_session["session_id"]
    # Account photos are restored, but the previous test's manual choice is not.
    assert sources(client.get(f"/api/v1/selfit/sessions/{fresh['sessionId']}/suit").json()) == dict.fromkeys(FIELDS, "photo")


def test_profile_api_saving_one_field_does_not_mark_prefilled_fields(client, photo_session, field):
    data = make_data(photo_session, onboarding._profile_snapshot(photo_session))
    onboarding._write_store(data)
    response = client.patch("/api/v1/selfit/me/profile", headers={"If-Match": "1"},
                            json={"reportId": "rep_provenance", "manual": {field: CHOICES[field]}})
    assert response.status_code == 200
    assert sources(response.json()["profile"]["suit"]) == {key: "manual" if key == field else "photo" for key in FIELDS}

class ManualProvenanceTests(unittest.TestCase):
    pass


def regression_case(check, parameters):
    def run(self):
        with isolated_client() as client:
            available = {"client": client, "photo_session": photo_session(), **parameters}
            check(**{key: available[key] for key in inspect.signature(check).parameters})
    return run


for name, check in list(globals().items()):
    if not name.startswith("test_") or not callable(check):
        continue
    arguments = inspect.signature(check).parameters
    cases = ([{"field": field} for field in FIELDS] if "field" in arguments else
             [{"kind": "face", "cleared": ("skin", "faceShape")},
              {"kind": "body", "cleared": ("bodyShape",)}] if "kind" in arguments else [{}])
    for index, parameters in enumerate(cases):
        setattr(ManualProvenanceTests, f"{name}_{index}", regression_case(check, parameters))


if __name__ == "__main__":
    unittest.main()

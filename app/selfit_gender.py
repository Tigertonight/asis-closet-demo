"""Account gender is a declared profile value, independent of login and report snapshots."""
from datetime import datetime, timezone

GENDERS = ("female", "male")


def declared_profile(data: dict, user_id: str) -> dict:
    if not user_id:
        return {}
    saved = next((p for p in data.get("user_profiles", []) if p.get("user_id") == user_id), None)
    if saved and saved.get("gender") in GENDERS:
        return saved
    # Recover pre-profile selections without treating the auth default as a choice.
    candidates = []
    for session in data.get("sessions", []):
        if session.get("user_id") == user_id and session.get("gender") in GENDERS:
            candidates.append((session.get("gender_selected_at") or session.get("created_at") or "", session["gender"]))
    for report in data.get("reports", []):
        gender = (report.get("profile") or {}).get("gender") or (report.get("data") or {}).get("gender")
        if report.get("user_id") == user_id and gender in GENDERS:
            candidates.append((report.get("created_at") or "", gender))
    if not candidates:
        return {}
    when, gender = max(candidates, key=lambda pair: pair[0])
    return {"user_id": user_id, "gender": gender, "gender_revision": 0, "gender_updated_at": when}


def save_gender(data: dict, user_id: str, gender: str) -> dict:
    if gender not in GENDERS:
        raise ValueError("Invalid gender")
    previous = declared_profile(data, user_id)
    profiles = data.setdefault("user_profiles", [])
    entry = next((p for p in profiles if p.get("user_id") == user_id), None)
    if entry is None:
        entry = {"user_id": user_id}
        profiles.append(entry)
    entry.update(gender=gender, gender_revision=int(previous.get("gender_revision", 0)) + 1,
                 gender_updated_at=datetime.now(timezone.utc).isoformat())
    return entry


def account_gender(user: dict) -> str:
    from app.selfit_onboarding import _load_store
    selected = declared_profile(_load_store(), str(user.get("user_id") or ""))
    return selected.get("gender") or ("male" if user.get("gender") == "male" else "female")

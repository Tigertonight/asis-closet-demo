"""Persona notebook photographs, distinct from structured garment outfits."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool

from app.auth import get_current_user
from app.material_assets import resolve_image_references
from app.recommendation_profile import resolve_profile
from app.selfit_report import _personality_template_catalog
from app.storage import storage_context, user_storage

router = APIRouter(prefix="/selfit/try-on/inspiration-notes")


def persona_notes(persona: str) -> list[dict]:
    template = resolve_image_references(_personality_template_catalog()["types"].get(persona, {}))
    items = template.get("recommendations", {}).get("outfits", {}).get("items", [])
    notes = []
    for item in items:
        image = item.get("image") or {}
        if not image.get("src"):
            continue
        source = re.search(r"https://[^\s<>]+", item.get("sourceUrl") or "")
        notes.append({
            "id": f"note:{persona}:{item['id']}", "kind": "note", "persona": persona,
            "title": item.get("name") or "穿搭灵感", "byline": item.get("byline") or "",
            "image_url": image["src"], "width": image.get("width"), "height": image.get("height"),
            "source_url": source.group(0) if source else "", "favorite": False,
        })
    return notes


def _favorites():
    path = storage_context().user_root / "inspiration-notes.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS favorites (note_id TEXT PRIMARY KEY)")
    return db


@router.get("")
def list_notes(current_user: dict = Depends(get_current_user)):
    with user_storage(current_user["user_id"]):
        persona = resolve_profile(current_user["user_id"]).get("persona_id")
        notes = persona_notes(persona) if persona else []
        db = _favorites()
        try:
            saved = {row[0] for row in db.execute("SELECT note_id FROM favorites")}
        finally:
            db.close()
        saved_notes = [
            {**note, "favorite": True}
            for code in _personality_template_catalog()["types"]
            for note in persona_notes(code) if note["id"] in saved
        ]
        return {"notes": [{**note, "favorite": note["id"] in saved} for note in notes],
                "saved_notes": saved_notes,
                "persona": persona, "profile_required": not bool(persona)}


class FavoriteUpdate(BaseModel):
    favorite: StrictBool


@router.patch("/{note_id}/favorite")
def save_note(note_id: str, payload: FavoriteUpdate, current_user: dict = Depends(get_current_user)):
    with user_storage(current_user["user_id"]):
        persona = resolve_profile(current_user["user_id"]).get("persona_id")
        note = next((row for code in _personality_template_catalog()["types"]
                     for row in persona_notes(code) if row["id"] == note_id), None)
        db = _favorites()
        try:
            already_saved = db.execute("SELECT 1 FROM favorites WHERE note_id = ?", (note_id,)).fetchone()
            if note is None or (note["persona"] != persona and not already_saved):
                raise HTTPException(404, "这条穿搭灵感暂时不可用，请刷新灵感库。")
            with db:
                if payload.favorite:
                    db.execute("INSERT OR IGNORE INTO favorites VALUES (?)", (note_id,))
                else:
                    db.execute("DELETE FROM favorites WHERE note_id = ?", (note_id,))
        finally:
            db.close()
        return {**note, "favorite": payload.favorite}

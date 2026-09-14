"""Resolve the exact report notebook cards to delivered, structured try-on outfits."""
from __future__ import annotations

import re
import random
import fcntl
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.material_assets import asset_content_url, write_json_atomic
from app.storage import storage_context
from app.selfit_gender import declared_profile
from app.selfit_report import _personality_template_catalog, report_for_gender
from app.styling_catalog import adapt_outfit, delivery_looks, outfit_id

router = APIRouter(prefix="/selfit/try-on/report-outfits")


def _note_outfit(look: dict, note: dict) -> dict:
    binding = look["note_binding"]
    asset_id = look["source_asset"]["assetId"]
    source = re.search(r"https://[^\s<>]+", note.get("sourceUrl") or "")
    return {**adapt_outfit(look), "report_note": {
        "id": f"note:{binding['templateId']}:{binding['noteId']}", "kind": "note",
        "persona": binding["persona"], "template_id": binding["templateId"],
        "title": note["name"], "byline": note.get("byline", ""),
        "image_url": asset_content_url(asset_id), "image_asset_id": asset_id,
        "width": note["image"].get("width"), "height": note["image"].get("height"),
        "source_url": source.group(0) if source else "", "favorite": False,
    }}


def _home_candidates(current_user: dict) -> list[tuple[dict, dict]]:
    catalog = _personality_template_catalog()
    templates = {**catalog.get("types", {}), **catalog.get("variants", {})}
    candidates = []
    male = current_user.get("gender") == "male"
    for look in delivery_looks():
        binding = look["note_binding"]
        if (binding.get("gender") == "male") != male:
            continue
        notes = templates.get(binding["templateId"], {}).get("recommendations", {}).get("outfits", {}).get("items", [])
        note = next((n for n in notes if n["id"] == binding["noteId"]), None)
        if note and note["image"].get("assetId") == look["source_asset"]["assetId"] and note["name"] == binding["name"]:
            candidates.append((look, note))
    return candidates


@router.get("/random")
def random_home_notes(
    selected_outfit_id: str | None = Query(default=None, max_length=160),
    current_user: dict = Depends(get_current_user),
):
    """Legacy sampler. A pinned note must still belong to the account's gender."""
    try:
        candidates = _home_candidates(current_user)
        pinned = next((pair for pair in candidates if outfit_id(pair[0]) == selected_outfit_id), None)
        # Some templates share a notebook photo. Show it only once in the strip.
        unique = {pair[0]["source_asset"]["assetId"]: pair for pair in candidates}
        if pinned:
            unique.pop(pinned[0]["source_asset"]["assetId"], None)
        selected = ([pinned] if pinned else []) + random.sample(list(unique.values()), min(3 if pinned else 4, len(unique)))
        if len(selected) != 4:
            raise ValueError("Four distinct delivered notebooks are required")
        return {"mode": "live", "outfits": [_note_outfit(look, note) for look, note in selected]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "穿搭笔记暂时无法加载，请稍后重试。") from exc


def _initial_home_notes(current_user: dict, saved: dict | None) -> dict:
    """Use the latest completed report; never pin an unrelated selected outfit."""
    try:
        if saved is None:
            return {**random_home_notes(None, current_user), "source": "random"}

        # Authentication resolves the current declaration; saved reports are snapshots.
        report = report_for_gender(saved["data"], current_user.get("gender"))
        persona = str(report["typeId"]).strip().lower()
        gender = report.get("gender") or current_user.get("gender")
        key = str(report.get("templateId") or (f"{persona}-male" if gender == "male" else persona)).strip().lower()
        catalog = _personality_template_catalog()
        template = {**catalog.get("types", {}), **catalog.get("variants", {})}.get(key, {})
        if gender == "male" and not template and key == f"{persona}-male":
            return {**random_home_notes(None, {**current_user, "gender": "male"}),
                    "source": "gender_library", "persona": persona,
                    "notice": "这个型格的男生穿搭正在准备中，先试试男生穿搭参考。"}
        notes = template.get("recommendations", {}).get("outfits", {}).get("items", [])
        ids = [note["id"] for note in notes]
        if template.get("typeId") != persona or len(ids) != 4 or len(set(ids)) != 4:
            raise ValueError("No complete four-note template for this report")
        saved_ids = [note.get("id") for note in report.get("outfits") or []]
        if len(saved_ids) == 4 and set(saved_ids) == set(ids):
            ids = saved_ids
        # Resolve current delivered assets, while keeping this report's template/order.
        # An unrelated selected outfit must never displace one of these four notes.
        return {**report_outfits(persona, ids, key), "source": "report"}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "你的型格穿搭暂时无法加载，请稍后重试。") from exc


def _home_notes_path(user_id: str):
    return storage_context(user_id).user_root / "home-recommendations.json"


def home_notes(current_user: dict, selected_outfit_id: str | None = None, *, refresh: bool = False) -> dict:
    """Persist note identities, not photos/URLs. Only explicit refresh advances a batch.

    A new report or gender resets the initial batch. Resolve current delivered
    items on every read so stored recommendations cannot serve stale cutouts.
    The selected try-on outfit is deliberately independent of this list.
    """
    from app.selfit_onboarding import _account_profile_report, _load_store

    try:
        path = _home_notes_path(current_user["user_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        # Cross-worker serialization plus atomic replacement prevents a partial
        # batch, duplicate first loads, or two requests losing the seen history.
        with path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            store = _load_store()
            profile = declared_profile(store, current_user["user_id"])
            current_user = {**current_user, "gender": profile.get("gender") or current_user.get("gender")}
            saved = _account_profile_report(store, current_user["user_id"])
            data = (saved or {}).get("data") or {}
            context = hashlib.sha256(json.dumps([
                current_user["user_id"], current_user.get("gender") or "female",
                profile.get("gender_revision", 0),
                (saved or {}).get("report_id"), (saved or {}).get("created_at"),
                data.get("typeId"), data.get("templateId"), data.get("outfits"),
            ], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            stored = json.loads(path.read_text()) if path.exists() else {}
            if stored.get("context") != context or stored.get("version") != 1:
                stored = {}
            if stored and not refresh:
                pairs = {(look["note_binding"]["templateId"], note["id"]): (look, note)
                         for look, note in _home_candidates(current_user)}
                rows = []
                for identity in stored["notes"]:
                    look, note = pairs[(identity["template_id"], identity["note_id"])]
                    if look["source_asset"]["assetId"] != identity["asset_id"]:
                        raise ValueError("The saved notebook photo has changed")
                    rows.append(_note_outfit(look, note))
                if len(rows) != 4 or len({row["source_asset_id"] for row in rows}) != 4:
                    raise ValueError("Incomplete saved batch")
                return {**stored["metadata"], "mode": "live", "outfits": rows}

            seen = set(stored.get("seen") or [])
            if refresh:
                unique = {look["source_asset"]["assetId"]: (look, note)
                          for look, note in _home_candidates(current_user)}
                # Mark the initial report's notes as seen even for a direct POST.
                initial = None if stored else _initial_home_notes(current_user, saved)
                previous = {row["asset_id"] for row in stored.get("notes", [])} if stored else {
                    row["source_asset_id"] for row in initial["outfits"]}
                seen |= previous
                fresh = [key for key in unique if key not in seen]
                chosen = random.sample(fresh, min(4, len(fresh)))
                if len(chosen) < 4:
                    # Finish the unseen cycle, then refill without repeating the
                    # immediately previous batch whenever the pool permits it.
                    refill = [key for key in unique if key not in previous and key not in chosen]
                    if len(refill) < 4 - len(chosen):
                        refill += [key for key in unique if key in previous and key not in chosen]
                    chosen += random.sample(refill, 4 - len(chosen))
                    seen = set(chosen)
                else:
                    seen.update(chosen)
                result = {"mode": "live", "source": "explore",
                          "outfits": [_note_outfit(*unique[key]) for key in chosen]}
            else:
                result = _initial_home_notes(current_user, saved)
                seen = {row["source_asset_id"] for row in result["outfits"]}
            rows = result["outfits"]
            write_json_atomic(path, {
                "version": 1, "context": context,
                "metadata": {key: value for key, value in result.items() if key not in {"outfits", "mode"}},
                "notes": [{"template_id": row["report_note"]["template_id"],
                           "note_id": row["report_note"]["id"].split(":")[-1],
                           "asset_id": row["source_asset_id"]} for row in rows],
                "seen": sorted(seen),
            })
            return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "穿搭笔记暂时无法加载，请稍后重试。") from exc


@router.get("/home")
def list_home_notes(
    selected_outfit_id: str | None = Query(default=None, max_length=160),
    current_user: dict = Depends(get_current_user),
):
    return JSONResponse(home_notes(current_user, selected_outfit_id), headers={"Cache-Control": "private, no-store"})


@router.post("/home/refresh")
def refresh_home_notes(current_user: dict = Depends(get_current_user)):
    return JSONResponse(home_notes(current_user, refresh=True), headers={"Cache-Control": "private, no-store"})


def report_outfits(persona: str, note_ids: list[str], template_id: str | None = None,
                   note_assets: list[str] | None = None) -> dict:
    if not 1 <= len(note_ids) <= 4 or len(set(note_ids)) != len(note_ids):
        raise HTTPException(422, "请选择报告中的一到四篇穿搭笔记。")
    if note_assets is not None and len(note_assets) != len(note_ids):
        raise HTTPException(422, "报告笔记与图片数量不一致，请返回报告重试。")
    catalog = _personality_template_catalog()
    key = template_id or persona
    template = {**catalog.get("types", {}), **catalog.get("variants", {})}.get(key, {})
    if template.get("typeId") != persona:
        raise HTTPException(404, "这份风格报告暂时不可用，请返回报告重试。")
    notes = {item["id"]: item for item in template.get("recommendations", {}).get("outfits", {}).get("items", [])}
    if any(note_id not in notes for note_id in note_ids):
        raise HTTPException(404, "这篇穿搭笔记暂时不可用，请返回报告重试。")
    try:
        bindings = {(look["note_binding"]["templateId"], look["note_binding"]["noteId"]): look for look in delivery_looks()}
        outfits = []
        for index, note_id in enumerate(note_ids):
            look = bindings[(key, note_id)]
            note = notes[note_id]
            asset_id = look["source_asset"]["assetId"]
            if note["image"]["assetId"] != asset_id or note["name"] != look["note_binding"]["name"]:
                raise ValueError("Delivery no longer matches the report template")
            # Old reports sent the literal "legacy" when no asset identity was
            # stored. Resolve those stable notebook IDs against this template;
            # a concrete but different asset ID must still fail the version check.
            if note_assets is not None and note_assets[index] not in {"legacy", asset_id}:
                raise HTTPException(409, "报告穿搭素材已更新，请重新生成报告后再试。")
            outfits.append(_note_outfit(look, note))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "报告搭配的素材暂时无法加载，请稍后重试。") from exc
    return {"persona": persona, "template_id": key, "mode": "live", "outfits": outfits,
            "resolved_legacy_assets": bool(note_assets and "legacy" in note_assets)}


@router.get("")
def list_report_outfits(
    persona: str = Query(min_length=1, max_length=20),
    note_ids: str = Query(min_length=1, max_length=200),
    template_id: str | None = Query(default=None, min_length=1, max_length=40),
    note_assets: str | None = Query(default=None, min_length=1, max_length=300),
    current_user: dict = Depends(get_current_user),
):
    return report_outfits(persona.strip().lower(), note_ids.split(","),
                          template_id.strip().lower() if template_id else None,
                          note_assets.split(",") if note_assets is not None else None)

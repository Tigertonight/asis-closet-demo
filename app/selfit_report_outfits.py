"""Resolve the exact report notebook cards to delivered, structured try-on outfits."""
from __future__ import annotations

import re
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.material_assets import asset_content_url
from app.selfit_report import _personality_template_catalog
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


@router.get("/random")
def random_home_notes(
    selected_outfit_id: str | None = Query(default=None, max_length=160),
    current_user: dict = Depends(get_current_user),
):
    """Sample four real notebook photos; retain a selected note on page refresh."""
    try:
        catalog = _personality_template_catalog()
        templates = {**catalog.get("types", {}), **catalog.get("variants", {})}
        candidates = []
        for look in delivery_looks():
            binding = look["note_binding"]
            notes = templates.get(binding["templateId"], {}).get("recommendations", {}).get("outfits", {}).get("items", [])
            note = next((n for n in notes if n["id"] == binding["noteId"]), None)
            if note and note["image"].get("assetId") == look["source_asset"]["assetId"] and note["name"] == binding["name"]:
                candidates.append((look, note))
        pinned = next((pair for pair in candidates if outfit_id(pair[0]) == selected_outfit_id), None)
        # Keep an explicitly opened outfit, but sample new suggestions for the account.
        male = current_user.get("gender") == "male" and any(t.get("gender") == "male" for t in templates.values())
        candidates = [pair for pair in candidates if (pair[0]["note_binding"].get("gender") == "male") == male]
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


def home_notes(current_user: dict, selected_outfit_id: str | None = None) -> dict:
    """Use this account's latest completed report, without loading its photos."""
    from app.selfit_onboarding import _account_profile_report, _load_store

    try:
        saved = _account_profile_report(_load_store(), current_user["user_id"])
        if saved is None:
            return {**random_home_notes(selected_outfit_id, current_user), "source": "random"}

        report = saved["data"]
        persona = str(report["typeId"]).strip().lower()
        gender = report.get("gender") or current_user.get("gender")
        key = str(report.get("templateId") or (f"{persona}-male" if gender == "male" else persona)).strip().lower()
        catalog = _personality_template_catalog()
        template = {**catalog.get("types", {}), **catalog.get("variants", {})}.get(key, {})
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


@router.get("/home")
def list_home_notes(
    selected_outfit_id: str | None = Query(default=None, max_length=160),
    current_user: dict = Depends(get_current_user),
):
    return JSONResponse(home_notes(current_user, selected_outfit_id), headers={"Cache-Control": "private, no-store"})


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

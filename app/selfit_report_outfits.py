"""Resolve the exact report notebook cards to delivered, structured try-on outfits."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.material_assets import asset_content_url
from app.selfit_report import _personality_template_catalog
from app.styling_catalog import adapt_outfit, delivery_looks

router = APIRouter(prefix="/selfit/try-on/report-outfits")


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
            source = re.search(r"https://[^\s<>]+", note.get("sourceUrl") or "")
            outfits.append({**adapt_outfit(look), "report_note": {
                "id": f"note:{key}:{note_id}", "kind": "note", "persona": persona, "template_id": key,
                "title": note["name"], "byline": note.get("byline", ""),
                "image_url": asset_content_url(asset_id), "image_asset_id": asset_id,
                "width": note["image"].get("width"), "height": note["image"].get("height"),
                "source_url": source.group(0) if source else "", "favorite": False,
            }})
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

"""Scene, trend and personality collections for the inspiration library."""
from __future__ import annotations

import json
from pathlib import Path

from app.material_assets import asset_content_url

DELIVERY_PATH = Path(__file__).resolve().parent / "data/inspiration-styling-delivery.v1.json"
TEMPLATE_PREFIX = "inspiration_"


def inspiration_delivery() -> dict:
    data = json.loads(DELIVERY_PATH.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != "1.0" or data.get("uploadStatus") != "verified":
        raise ValueError("Inspiration assets have not been verified")
    topics = {topic["id"]: topic for topic in data["topics"]}
    if len(topics) != len(data["topics"]):
        raise ValueError("Duplicate inspiration topic")
    seen = set()
    for look in data["looks"]:
        binding = look["note_binding"]
        topic = look["inspiration_binding"]["topicId"]
        if topic not in topics or binding["templateId"] != TEMPLATE_PREFIX + topic:
            raise ValueError("Invalid inspiration binding")
        identity = (binding["templateId"], binding["noteId"])
        ids = [item["item_id"] for item in look["items"]]
        layers = look["layer_sequence_inner_to_outer"]
        if identity in seen or not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids):
            raise ValueError("Duplicate or invalid inspiration look")
        if set(layers) != set(ids) or len(layers) != len(ids):
            raise ValueError("Incomplete inspiration layering sequence")
        seen.add(identity)
    return data


def inspiration_looks() -> list[dict]:
    return inspiration_delivery()["looks"]


def inspiration_topics() -> dict:
    from app.selfit_report import _personality_template_catalog
    from app.styling_catalog import adapt_outfit, delivery_looks

    data = inspiration_delivery()
    topics = []
    for topic in data["topics"]:
        looks = sorted((look for look in data["looks"]
                        if look["inspiration_binding"]["topicId"] == topic["id"]),
                       key=lambda look: look["note_binding"]["position"])
        outfits = [adapt_outfit(look) for look in looks]
        topics.append({"id": topic["id"], "title": topic["title"], "kind": topic["kind"],
                       "cover": asset_content_url(topic["coverAssetId"]),
                       "previews": [outfit["cover_path"] for outfit in outfits[1:4]],
                       "outfits": outfits})
    templates = _personality_template_catalog()["types"]
    persona_looks = delivery_looks()
    if {look["note_binding"]["persona"] for look in persona_looks} != set(templates):
        raise ValueError("Personality collections do not match the report catalog")
    for code, template in sorted(templates.items(), key=lambda row: row[1]["index"]):
        looks = sorted((look for look in persona_looks if look["note_binding"]["persona"] == code),
                       key=lambda look: (look["note_binding"].get("gender") == "male",
                                         look["note_binding"]["bodyProfile"] != "standard",
                                         look["note_binding"]["templateId"], look["note_binding"]["position"]))
        outfits = [{**adapt_outfit(look), "body_profile": look["note_binding"]["bodyProfile"]}
                   for look in looks]
        topics.append({"id": f"persona-{code}", "title": template["metadata"]["name"],
                       "kind": "persona", "persona": code, "cover": outfits[0]["cover_path"],
                       "previews": [outfit["cover_path"] for outfit in outfits[1:4]],
                       "outfits": outfits})
    return {"topics": topics, "total": sum(len(topic["outfits"]) for topic in topics)}

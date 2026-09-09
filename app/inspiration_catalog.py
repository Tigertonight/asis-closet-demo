"""Scene and trend deliveries for the inspiration library, separate from personas."""
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
    from app.styling_catalog import adapt_outfit

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
    return {"topics": topics, "total": len(data["looks"])}

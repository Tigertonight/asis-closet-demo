"""Keep a report audience distinct from its underlying personality code."""
from __future__ import annotations

import re


def template_identity(template: dict) -> tuple[str, str, str, str]:
    persona = str(template.get("code") or (template.get("masterData") or {}).get("typeId") or "").lower()
    if not re.fullmatch(r"[a-z]{4}", persona):
        raise ValueError(f"Invalid personality code: {persona}")
    # Older editor exports incorrectly persisted standard on the four curvy IDs.
    curvy_id = str(template.get("templateId") or "").lower() == f"{persona}-curvy"
    curvy_name = str(template.get("name") or "").endswith("-微胖")
    body = "curvy" if template.get("bodyProfile") == "curvy" or curvy_id or curvy_name else "standard"
    gender = template.get("gender") if template.get("gender") in {"male", "female"} else "unisex"
    key = persona + ("-curvy" if body == "curvy" else "") + (f"-{gender}" if gender != "unisex" else "")
    return persona, body, gender, key

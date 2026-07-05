from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

REPORT_PATH = ROOT / "outputs" / "closet_mvp_acceptance.json"


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    seed = int(datetime.now().timestamp()) % 80
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60 + seed, 105)
    return image


def main() -> int:
    client = TestClient(app)
    checks: list[dict[str, object]] = []

    capabilities = client.get("/closet/capabilities")
    checks.append({"name": "capabilities", "passed": capabilities.status_code == 200})

    upload = client.post(
        "/closet/import/upload",
        files=[("images", ("acceptance_top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )
    upload_ok = upload.status_code == 200 and upload.json().get("summary", {}).get("created", 0) >= 1
    checks.append({"name": "upload_auto_import", "passed": upload_ok})

    item = upload.json()["items"][0] if upload_ok else {}
    listed = client.get("/closet/items")
    checks.append({"name": "list_items", "passed": listed.status_code == 200 and listed.json().get("total", 0) >= 1})

    patched = client.patch(
        f"/closet/items/{item.get('item_id')}",
        json={"category": "top", "style_tags": ["acceptance"], "note": "验收样本"},
    ) if item else None
    checks.append({"name": "edit_item", "passed": bool(patched and patched.status_code == 200 and patched.json().get("note") == "验收样本")})

    person_path = ROOT / "tests" / "fixtures" / "tryon_models" / "male_medium_1.png"
    tryon = client.post(
        "/try-on",
        data={"closet_item_id": item.get("item_id", "")},
        files={"person_image": ("person.png", person_path.read_bytes(), "image/png")},
    ) if item else None
    checks.append({"name": "closet_item_enters_tryon", "passed": bool(tryon and tryon.status_code == 200 and tryon.json().get("input", {}).get("garment_image_id"))})

    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [item.get("item_id")], "title": "验收搭配", "scene_tags": ["acceptance"]},
    ) if item else None
    outfit_ok = bool(outfit and outfit.status_code == 200 and outfit.json().get("outfit_id"))
    checks.append({"name": "create_outfit", "passed": outfit_ok})

    outfit_tryon = client.post(
        "/try-on/from-outfit",
        data={"outfit_id": outfit.json().get("outfit_id", "")},
        files={"person_image": ("person.png", person_path.read_bytes(), "image/png")},
    ) if outfit_ok else None
    checks.append({"name": "outfit_enters_tryon", "passed": bool(outfit_tryon and outfit_tryon.status_code == 200 and outfit_tryon.json().get("mode") == "from_outfit")})

    mock_tryon = client.post(
        "/try-on/mock-from-outfit",
        data={"outfit_id": outfit.json().get("outfit_id", "")},
    ) if outfit_ok else None
    mock_ok = bool(mock_tryon and mock_tryon.status_code == 200 and mock_tryon.json().get("record", {}).get("image_path"))
    checks.append({"name": "outfit_mock_tryon_record", "passed": mock_ok})

    records = client.get("/closet/tryon-records")
    checks.append({"name": "list_tryon_records", "passed": bool(records.status_code == 200 and records.json().get("total", 0) >= 1)})

    reprocessed = client.post(f"/closet/items/{item.get('item_id')}/reprocess") if item else None
    checks.append({"name": "reprocess_item", "passed": bool(reprocessed and reprocessed.status_code == 200 and reprocessed.json().get("summary", {}).get("created", 0) >= 0)})

    deleted = client.delete(f"/closet/items/{item.get('item_id')}") if item else None
    checks.append({"name": "delete_item", "passed": bool(deleted and deleted.status_code == 200)})

    passed = all(bool(check["passed"]) for check in checks)
    report = {
        "status": "passed_for_validation" if passed else "failed",
        "checks": checks,
        "capabilities": capabilities.json() if capabilities.status_code == 200 else {},
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

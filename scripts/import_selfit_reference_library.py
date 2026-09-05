#!/usr/bin/env python3
"""Import the supplied outfit workbook and archive as a reference-only catalog.

The source photography is never copied into the public static tree.  Records
are explicitly non-publishable and exist only to inform original garment
briefs and persona coverage analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "app/static/selfit/data/reference-looks.internal.json"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", NS)).strip()
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return shared[int(value.text)].strip()
    return value.text.strip()


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    result = 0
    for char in (letters.group(0) if letters else "A"):
        result = result * 26 + ord(char) - 64
    return result - 1


def read_first_sheet(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as book:
        shared = _shared_strings(book)
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in sheet.findall(".//m:sheetData/m:row", NS):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            values[_column_index(cell.attrib.get("r", "A1"))] = _cell_text(cell, shared)
        if values:
            width = max(values) + 1
            rows.append([values.get(index, "") for index in range(width)])
    return rows


def _persona_code(value: str) -> str:
    match = re.search(r"\b([A-Z]{4,5})\b", value)
    return match.group(1) if match else ""


def _parts(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(workbook_path: Path, image_archive: Path) -> dict[str, Any]:
    rows = read_first_sheet(workbook_path)
    if not rows:
        raise ValueError("workbook contains no rows")
    headers = rows[0]
    expected_headers = ["图片", "博主", "笔记链接", "来源审美族群", "来源搜索词", "主人格", "次人格", "地域美学风格", "视觉重心", "腰线", "腹部空间", "线条方向", "体型标签", "笔记标题", "备注", "更新时间"]
    if headers[: len(expected_headers)] != expected_headers:
        raise ValueError(f"unexpected workbook headers: {headers}")

    with zipfile.ZipFile(image_archive) as archive:
        members = {
            Path(name).name: name
            for name in archive.namelist()
            if not name.startswith("__MACOSX/") and not name.endswith("/") and Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic"}
        }
        records: list[dict[str, Any]] = []
        for raw in rows[1:]:
            values = (raw + [""] * len(expected_headers))[: len(expected_headers)]
            item = dict(zip(expected_headers, values, strict=True))
            filename = item["图片"]
            member = members.get(filename)
            if not member:
                raise ValueError(f"missing image in archive: {filename}")
            digest = _sha256(archive.read(member))
            reference_id = "ref_" + hashlib.sha256(f"{filename}|{item['笔记链接']}".encode()).hexdigest()[:16]
            records.append({
                "id": reference_id,
                "file_name": filename,
                "archive_member": member,
                "sha256": digest,
                "creator": item["博主"],
                "source_url": item["笔记链接"],
                "source_aesthetic_cluster": item["来源审美族群"],
                "source_query": item["来源搜索词"],
                "primary_persona": _persona_code(item["主人格"]),
                "secondary_personas": [code for code in (_persona_code(part) for part in _parts(item["次人格"])) if code],
                "regional_styles": _parts(item["地域美学风格"]),
                "structure": {
                    "visual_weight": item["视觉重心"].replace("重心", ""),
                    "waistline": item["腰线"],
                    "tummy_space": "贴身" if item["腹部空间"] == "紧贴" else item["腹部空间"],
                    "line_direction": {"纵向延伸": "纵向", "横向切割": "横向", "普通": "无明显"}.get(item["线条方向"], item["线条方向"]),
                },
                "body_types": _parts(item["体型标签"]),
                "title": item["笔记标题"],
                "updated_at": item["更新时间"],
                "rights_status": "source_recorded",
                "publishable": False,
                "usage": "internal_style_reference_only",
            })

        used = {record["file_name"] for record in records}
        unlabeled = []
        for filename, member in sorted(members.items()):
            if filename in used:
                continue
            unlabeled.append({
                "id": "unlabeled_" + hashlib.sha256(filename.encode()).hexdigest()[:16],
                "file_name": filename,
                "archive_member": member,
                "sha256": _sha256(archive.read(member)),
                "status": "unlabeled",
                "rights_status": "source_recorded",
                "publishable": False,
            })

    persona_counts: dict[str, int] = {}
    for record in records:
        code = record["primary_persona"] or "UNKNOWN"
        persona_counts[code] = persona_counts.get(code, 0) + 1
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourceWorkbook": workbook_path.name,
        "sourceArchive": image_archive.name,
        "usagePolicy": "reference_only_not_for_publication",
        "summary": {
            "labeled": len(records),
            "unlabeled": len(unlabeled),
            "personaCounts": persona_counts,
        },
        "reference_looks": records,
        "unlabeled_assets": unlabeled,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("image_archive", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = build(args.workbook, args.image_archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **data["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

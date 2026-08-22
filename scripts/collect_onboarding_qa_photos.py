"""QA 素材搜集脚本：从 Unsplash 下载多样的大头照/全身照，经算法初筛后存入 qa_photos/。

用法：.venv/bin/python scripts/collect_onboarding_qa_photos.py
素材仅用于内部 QA 目检；manifest.json 记录来源 URL 以便溯源（Unsplash License）。
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_photos"
TMP = Path("/tmp/onboarding_qa_candidates")

FACE_QUERIES = [
    ("front portrait woman face", 6),
    ("front portrait man face", 5),
    ("asian woman face portrait", 4),
    ("dark skin portrait", 4),
    ("woman bangs fringe portrait", 3),
    ("elderly man portrait face", 2),
]
BODY_QUERIES = [
    ("full body woman standing front", 6),
    ("full body man standing front", 5),
    ("plus size woman full body", 4),
    ("woman fitted dress full body", 4),
    ("man suit full body front", 3),
]


def search(query: str, per_page: int) -> list[dict]:
    resp = httpx.get(
        "https://unsplash.com/napi/search/photos",
        params={"query": query, "per_page": per_page, "orientation": "portrait"},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def download(raw_url: str, width: int = 1000) -> Image.Image | None:
    resp = httpx.get(raw_url, params={"w": width, "q": 85, "fm": "jpg", "fit": "max"}, timeout=30.0, follow_redirects=True)
    if resp.status_code != 200 or len(resp.content) < 20_000:
        return None
    try:
        image = Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None
    if min(image.size) < 500:
        return None
    return image


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from app.attribute_pipeline import analyze_body_photo, analyze_face_photo

    TMP.mkdir(parents=True, exist_ok=True)
    (OUT / "face").mkdir(parents=True, exist_ok=True)
    (OUT / "body").mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for kind, queries in [("face", FACE_QUERIES), ("body", BODY_QUERIES)]:
        kept = 0
        seen_ids: set[str] = set()
        for query, per_page in queries:
            try:
                results = search(query, per_page)
            except Exception as exc:
                print(f"[{kind}] query {query!r} failed: {exc}")
                continue
            for item in results:
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                image = download(item["urls"]["raw"])
                if image is None:
                    continue
                analysis = analyze_face_photo(image) if kind == "face" else analyze_body_photo(image)
                attrs = {
                    name: {"label": attr.get("label"), "status": attr["status"], "confidence": attr.get("confidence")}
                    for name, attr in analysis.get("attributes", {}).items()
                }
                labels = {name: attr["label"] for name, attr in attrs.items() if attr.get("label")}
                # 初筛：至少一个属性出标签；门禁失败的图不留（刘海/侧脸等 QA 场景单独补）
                if not labels:
                    continue
                kept += 1
                filename = f"{kind}_{kept:02d}.jpg"
                image.save(OUT / kind / filename, "JPEG", quality=88)
                manifest.append(
                    {
                        "file": f"{kind}/{filename}",
                        "kind": kind,
                        "source_url": item["urls"]["raw"],
                        "author": (item.get("user") or {}).get("name"),
                        "query": query,
                        "alt": item.get("alt_description") or "",
                        "prescreen_labels": labels,
                        "prescreen_issues": [issue["code"] for issue in analysis.get("issues", [])],
                    }
                )
                print(f"[{kind}] keep {filename} query={query!r} labels={labels}")
                time.sleep(0.2)

    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: {len(manifest)} photos -> {OUT}")


if __name__ == "__main__":
    main()

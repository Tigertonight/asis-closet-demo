"""把存量 accepted 用户照片回填进 QA 数据集（一次性迁移脚本）。

新上传的照片在 selfit_onboarding accepted 路径自动归档（archive_user_photo）；
本脚本处理部署前已 accepted 的历史照片，同样按 app / mirror 来源标记。

用法（项目根目录）：
    .venv/bin/python scripts/backfill_qa_from_sessions.py          # 执行
    .venv/bin/python scripts/backfill_qa_from_sessions.py --dry    # 只看会归档哪些
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image

from app.qa_onboarding import archive_user_photo
from app.selfit_onboarding import PHOTO_SUPPORTED_FORMATS, SELFIT_ONBOARDING_ASSET_DIR, SELFIT_ONBOARDING_STORE_PATH


def main() -> None:
    dry = "--dry" in sys.argv
    data = json.loads(SELFIT_ONBOARDING_STORE_PATH.read_text(encoding="utf-8"))
    archived = skipped = missing = 0
    for record in data.get("sessions", []):
        mirror = record.get("source") == "mirror_handoff"
        source = "mirror" if mirror else "app"
        session_id = record.get("session_id") or ""
        for kind, photo in (record.get("photos") or {}).items():
            if not isinstance(photo, dict) or photo.get("status") != "accepted":
                continue
            asset_id = photo.get("asset_id")
            suffix = PHOTO_SUPPORTED_FORMATS.get(str(photo.get("format") or ""), ".jpg")
            path = SELFIT_ONBOARDING_ASSET_DIR / session_id / f"{asset_id}{suffix}"
            if not asset_id or not path.exists():
                missing += 1
                print(f"  [missing] {session_id} {kind}: {path.name}")
                continue
            if dry:
                print(f"  [dry] {session_id} {kind}: {source}")
                archived += 1
                continue
            try:
                with Image.open(path) as image:
                    if archive_user_photo(image.convert("RGB"), kind, source):
                        archived += 1
                    else:
                        skipped += 1
            except Exception as exc:
                missing += 1
                print(f"  [error] {session_id} {kind}: {exc}")
    print(f"回填完成：归档 {archived} 张，去重跳过 {skipped} 张，缺失/失败 {missing} 张")


if __name__ == "__main__":
    main()

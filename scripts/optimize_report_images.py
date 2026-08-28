"""把报告页大图批量转 WebP（hero/色卡/分享装饰）。

内测反馈：报告页 hero 图 1.6-2.1MB（1484x1072 PNG），香港服务器直出无
缓存头，上海用户加载 6-10s。PNG 对 AI 生成的照片类图片压缩极差。

转换策略：
- hero.png / share-ornament.png / color-card.png → 同名 .webp（q85）
- 原图保留不动（设计源文件），HTML/模板引用改为 .webp
- 视觉无损（q85 + method=6），体积约降 90%

用法（项目根目录）：
    .venv/bin/python scripts/optimize_report_images.py          # 执行
    .venv/bin/python scripts/optimize_report_images.py --dry    # 只看会转哪些
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "app" / "static" / "selfit" / "assets" / "personality"

# 需要转换的文件名（16 型目录下同名文件）
TARGET_FILES = ("hero.png", "share-ornament.png", "color-card.png")
WEBP_QUALITY = 85
WEBP_METHOD = 6


def convert(dry: bool = False) -> None:
    total_before = total_after = 0
    converted = skipped = 0
    for folder in sorted(ASSET_DIR.iterdir()):
        if not folder.is_dir():
            continue
        for name in TARGET_FILES:
            source = folder / name
            if not source.exists():
                continue
            target = source.with_suffix(".webp")
            if target.exists():
                skipped += 1
                continue
            before = source.stat().st_size
            if dry:
                print(f"[dry] {folder.name}/{name}: {before // 1024}KB → {target.name}")
                continue
            with Image.open(source) as image:
                # RGBA 照片类转有损 WebP 时保留 alpha
                image.save(target, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
            after = target.stat().st_size
            total_before += before
            total_after += after
            converted += 1
            print(f"{folder.name}/{name}: {before // 1024}KB → {after // 1024}KB（-{100 - after * 100 // before}%）")
    if not dry and converted:
        print(f"\n共 {converted} 张（跳过已存在 {skipped} 张）：{total_before // 1024}KB → {total_after // 1024}KB，总缩减 {100 - total_after * 100 // total_before}%")


if __name__ == "__main__":
    convert(dry="--dry" in sys.argv)

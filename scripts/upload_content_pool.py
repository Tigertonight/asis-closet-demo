"""把本地内容池图片同步到公开对象存储桶，并输出 CDN URL 清单。

内容池是报告推荐用的公开静态资源（妆容/发型/穿搭参考图等），与用户私有
照片资产分离存放：公开桶 + CDN 域名分发，前端直连 CDN 加载。

用法（依赖 .env 里的 SELFIT_S3_* 凭据）：

    python scripts/upload_content_pool.py ./content_pool \
        --bucket selfit-content --prefix report/v1 \
        --public-base https://cdn.example.com

执行后打印每个文件的 CDN URL，并把清单写入 ./content_pool/manifest.json，
报告 builder（app/selfit_report.py）按相对路径引用，经 content_url() 解析。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="本地内容池目录")
    parser.add_argument("--bucket", required=True, help="公开桶名（与用户资产桶分开）")
    parser.add_argument("--prefix", default="report/v1", help="对象 key 前缀")
    parser.add_argument("--public-base", default="", help="CDN 域名，用于输出 URL 清单")
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"[fail] 目录不存在: {args.source}")
        return 1

    files = sorted(
        path for path in args.source.rglob("*")
        if path.is_file() and path.suffix.lower() in CONTENT_TYPES
    )
    if not files:
        print(f"[fail] {args.source} 下没有可上传的图片（jpg/png/webp）")
        return 1

    import os

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["SELFIT_S3_ENDPOINT"],
        aws_access_key_id=os.environ["SELFIT_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["SELFIT_S3_SECRET_ACCESS_KEY"],
        region_name=os.getenv("SELFIT_S3_REGION") or None,
    )
    prefix = args.prefix.strip("/")
    public_base = args.public_base.rstrip("/")

    manifest: dict[str, str] = {}
    for path in files:
        relative = f"{prefix}/{path.name}"
        client.put_object(
            Bucket=args.bucket,
            Key=relative,
            Body=path.read_bytes(),
            ContentType=CONTENT_TYPES[path.suffix.lower()],
        )
        url = f"{public_base}/{relative}" if public_base else relative
        manifest[path.name] = url
        print(f"[ok] {path.name} -> {url}")

    manifest_path = args.source / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共上传 {len(manifest)} 个文件，清单写入 {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

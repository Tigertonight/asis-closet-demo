"""上传公开素材，并登记 assetId → URL（不用于用户私有照片）。

    python scripts/upload_content_pool.py ./content_pool --bucket selfit-content \
        --prefix report/v1 --public-base https://cdn.example.com

主清单默认 app/data/material-assets.v1.json；source/manifest.json 记录相对文件名
与 assetId。业务图片使用 {"assetId": "asset_..."}，不再保存 CDN URL。
相同文件内容复用 ID，修改图片生成新 ID；迁移 CDN 后重新上传即可更新 URL。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, asset_id_for_bytes, validate_public_url, write_json_atomic

CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class OssUploadClient:
    """Adapt the shared uploader to the native Alibaba OSS SDK."""
    def __init__(self, bucket: Any):
        self.bucket = bucket

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> Any:
        if Bucket != self.bucket.bucket_name:
            raise ValueError("Configured OSS bucket does not match upload destination")
        return self.bucket.put_object(Key, Body, headers={"Content-Type": ContentType})


def upload_directory(source: Path, *, client: Any, bucket: str, public_base: str,
                     prefix: str = "report/v1", registry: MaterialRegistry | None = None,
                     manifest_path: Path | None = None,
                     image_paths: list[Path] | None = None, workers: int = 1) -> dict[str, Any]:
    public_base = public_base.rstrip("/")
    validate_public_url(public_base)
    base_parts = urlsplit(public_base)
    if base_parts.scheme not in {"http", "https"} or base_parts.query or base_parts.fragment:
        raise ValueError("--public-base must be an HTTP(S) CDN base URL without query or fragment")
    prefix = prefix.strip("/")
    if ".." in prefix.split("/"):
        raise ValueError("Object prefix must not contain ..")
    if not source.is_dir():
        raise ValueError(f"Directory does not exist: {source}")
    files = sorted(path for path in (image_paths if image_paths is not None else source.rglob("*"))
                   if path.is_file() and path.suffix.lower() in CONTENT_TYPES)
    if not files:
        raise ValueError(f"No jpg/png/webp images in {source}")
    registry = registry or MaterialRegistry()
    manifest_path = manifest_path or source / "manifest.json"
    manifest: dict[str, Any] = {"schemaVersion": "1.0", "files": {}}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("schemaVersion") == "1.0" and isinstance(previous.get("files"), dict):
            manifest = previous
    if not 1 <= workers <= 8:
        raise ValueError("Upload workers must be between 1 and 8")
    jobs: dict[str, tuple[Path, str, str, str]] = {}
    references: dict[str, list[str]] = {}
    for path in files:
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("Image symlink points outside the upload directory")
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes()
        asset_id = asset_id_for_bytes(data)
        content_type = CONTENT_TYPES[path.suffix.lower()]
        # Content keys avoid basename collisions and permit safe retries.
        suffix = ".jpg" if content_type == "image/jpeg" else path.suffix.lower()
        key = "/".join(part for part in (prefix, asset_id + suffix) if part)
        url = f"{public_base}/{quote(key, safe='/')}"
        validate_public_url(url)
        jobs.setdefault(asset_id, (path, key, url, content_type))
        references.setdefault(asset_id, []).append(relative)

    def upload(asset_id: str) -> str:
        path, key, url, content_type = jobs[asset_id]
        try:
            already_uploaded = registry.get(asset_id)["url"] == url
        except KeyError:
            already_uploaded = False
        if not already_uploaded:
            data = path.read_bytes()
            if asset_id_for_bytes(data) != asset_id:
                raise ValueError("Source image changed during upload")
            client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
            # Failed uploads never publish a new URL; each success is durable.
            storage = client.storage_metadata(key) if hasattr(client, "storage_metadata") else None
            registry.register(data, url, content_type, storage=storage)
        return asset_id

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for asset_id in executor.map(upload, jobs):
            for relative in references[asset_id]:
                manifest["files"][relative] = {"assetId": asset_id}
                print(f"[ok] {relative} -> {asset_id}", flush=True)
            write_json_atomic(manifest_path, manifest)
    return manifest


def main() -> int:
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="本地公开素材目录")
    parser.add_argument("--bucket", required=True, help="公开桶名（与用户资产桶分开）")
    parser.add_argument("--prefix", default="report/v1", help="对象 key 前缀")
    parser.add_argument("--public-base", required=True, help="CDN HTTP(S) 地址")
    parser.add_argument("--registry", type=Path, help="素材 JSON 路径（默认 app/data/material-assets.v1.json）")
    parser.add_argument("--backend", choices=("s3", "oss", "qiniu"), default="s3")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--manifest", type=Path, help="输出文件映射的位置；可保留源目录只读")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    if args.backend == "qiniu":
        from scripts.qiniu_material_upload import qiniu_client_from_env
        client = qiniu_client_from_env(args.bucket)
    elif args.backend == "oss":
        from app.selfit_assets import _oss_bucket_from_env
        client = OssUploadClient(_oss_bucket_from_env())
    else:
        import boto3
        client = boto3.client(
            "s3", endpoint_url=os.getenv("SELFIT_S3_ENDPOINT") or None,
            aws_access_key_id=os.getenv("SELFIT_S3_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("SELFIT_S3_SECRET_ACCESS_KEY") or None,
            region_name=os.getenv("SELFIT_S3_REGION") or None,
        )
    registry = MaterialRegistry(args.registry)
    manifest = upload_directory(args.source, client=client, bucket=args.bucket,
                                prefix=args.prefix, public_base=args.public_base, registry=registry,
                                manifest_path=args.manifest, workers=args.workers)
    print(f"[ok] {len(manifest['files'])} 个文件；素材 JSON: {registry.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

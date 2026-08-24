"""selfit onboarding 数据资产存储层（用户原图 / 分享图）。

资产策略：只增不删、精心保留（见 selfit_onboarding.py 顶部注释）。
本地目录是一等公民：即使启用 OSS，本地也作为写入缓冲与读取缓存保留，
OSS 为持久化主存。资产从本地到 OSS 的同步以本地目录为源。

后端切换（环境变量）：

    SELFIT_ASSET_STORE=local | oss | s3       # 默认 local
    # oss = 阿里云 OSS（oss2）；s3 = S3 兼容平台（boto3），覆盖
    # 七牛 Kodo / Cloudflare R2 / Backblaze B2 / 腾讯 COS 等。
    SELFIT_OSS_ENDPOINT=oss-cn-xxx.aliyuncs.com
    SELFIT_OSS_BUCKET=selfit-assets
    SELFIT_OSS_ACCESS_KEY_ID=...
    SELFIT_OSS_ACCESS_KEY_SECRET=...
    SELFIT_OSS_PREFIX=selfit/onboarding       # 可选，对象 key 前缀
    SELFIT_OSS_PUBLIC_BASE_URL=https://cdn.example.com/selfit  # 可选；
    # 配置后下载接口直接 302 到该 URL（CDN/公开桶），未配置则回源本地缓存。
    # s3 后端对应变量为 SELFIT_S3_ENDPOINT / BUCKET / ACCESS_KEY_ID /
    # SECRET_ACCESS_KEY / REGION（可选）/ PREFIX / PUBLIC_BASE_URL。

OSS 依赖 `oss2`、S3 依赖 `boto3`（requirements-ai.txt，可选运行时依赖），
未安装且启用对应后端时会在首次写入时给出明确报错，不影响 local 模式。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from app.storage import ROOT_DIR

DEFAULT_ASSET_DIR = ROOT_DIR / "outputs" / "selfit_onboarding" / "assets"


class AssetStore(Protocol):
    def save(self, key: str, content: bytes, content_type: str) -> None: ...

    def local_path(self, key: str) -> Path | None:
        """可用于 FileResponse 的本地路径；无本地副本时返回 None。"""

    def public_url(self, key: str) -> str | None:
        """可直接跳转的外部 URL（CDN/公开桶）；未配置时返回 None。"""

    def delete(self, key: str) -> None:
        """删除资产。资产默认只增不删，唯一的例外是用户主动删除自己的数据
        （隐私契约要求）；不得用于任何定期清理任务。"""


class LocalAssetStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root / key

    def save(self, key: str, content: bytes, content_type: str) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f"{target.name}.{os.urandom(6).hex()}.tmp")
        tmp_path.write_bytes(content)
        tmp_path.replace(target)

    def local_path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def public_url(self, key: str) -> str | None:
        return None

    def delete(self, key: str) -> None:
        (self._path(key)).unlink(missing_ok=True)
        parent = self._path(key).parent
        if parent != self._root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


_OSS_CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _oss_bucket_from_env() -> Any:
    try:
        import oss2
    except ImportError as exc:  # pragma: no cover - 取决于可选依赖
        raise RuntimeError("SELFIT_ASSET_STORE=oss 需要安装 oss2（见 requirements-ai.txt）") from exc
    endpoint = os.environ["SELFIT_OSS_ENDPOINT"]
    bucket_name = os.environ["SELFIT_OSS_BUCKET"]
    auth = oss2.Auth(
        os.environ["SELFIT_OSS_ACCESS_KEY_ID"],
        os.environ["SELFIT_OSS_ACCESS_KEY_SECRET"],
    )
    return oss2.Bucket(auth, endpoint, bucket_name)


class OssAssetStore:
    """本地缓存 + OSS 主存双写。delete 仅用于用户主动删除（隐私契约），不做任何定期清理。"""

    def __init__(self, cache_dir: Path, bucket: Any, prefix: str = "", public_base_url: str = "") -> None:
        self._cache = LocalAssetStore(cache_dir)
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._public_base_url = public_base_url.rstrip("/")

    def _object_key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def save(self, key: str, content: bytes, content_type: str) -> None:
        # 先落本地缓存（保证读取路径永远可用），再上传 OSS 持久化。
        self._cache.save(key, content, content_type)
        headers = {"Content-Type": content_type or _OSS_CONTENT_TYPES.get(Path(key).suffix, "application/octet-stream")}
        self._bucket.put_object(self._object_key(key), content, headers=headers)

    def local_path(self, key: str) -> Path | None:
        return self._cache.local_path(key)

    def public_url(self, key: str) -> str | None:
        if not self._public_base_url:
            return None
        return f"{self._public_base_url}/{self._object_key(key)}"

    def delete(self, key: str) -> None:
        self._cache.delete(key)
        self._bucket.delete_object(self._object_key(key))


def _s3_client_from_env() -> tuple[Any, str]:
    """构造 S3 兼容客户端，返回 (client, bucket)。

    覆盖七牛 Kodo / Cloudflare R2 / Backblaze B2 / 腾讯 COS 等 S3 兼容平台。
    """

    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - 取决于可选依赖
        raise RuntimeError("SELFIT_ASSET_STORE=s3 需要安装 boto3（见 requirements-ai.txt）") from exc
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["SELFIT_S3_ENDPOINT"],
        aws_access_key_id=os.environ["SELFIT_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["SELFIT_S3_SECRET_ACCESS_KEY"],
        region_name=os.getenv("SELFIT_S3_REGION") or None,
    )
    return client, os.environ["SELFIT_S3_BUCKET"]


class S3AssetStore:
    """本地缓存 + S3 兼容对象存储双写。delete 仅用于用户主动删除（隐私契约）。"""

    def __init__(self, cache_dir: Path, client: Any, bucket: str, prefix: str = "", public_base_url: str = "") -> None:
        self._cache = LocalAssetStore(cache_dir)
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._public_base_url = public_base_url.rstrip("/")

    def _object_key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def save(self, key: str, content: bytes, content_type: str) -> None:
        # 先落本地缓存（保证读取路径永远可用），再上传对象存储持久化。
        self._cache.save(key, content, content_type)
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._object_key(key),
            Body=content,
            ContentType=content_type or _OSS_CONTENT_TYPES.get(Path(key).suffix, "application/octet-stream"),
        )

    def local_path(self, key: str) -> Path | None:
        return self._cache.local_path(key)

    def public_url(self, key: str) -> str | None:
        if not self._public_base_url:
            return None
        return f"{self._public_base_url}/{self._object_key(key)}"

    def delete(self, key: str) -> None:
        self._cache.delete(key)
        self._client.delete_object(Bucket=self._bucket, Key=self._object_key(key))


def asset_store_from_env(cache_dir: Path | None = None) -> AssetStore:
    """按环境变量解析资产后端；每次调用读取 env，便于测试与运行时切换。"""

    cache_dir = cache_dir or DEFAULT_ASSET_DIR
    backend = os.getenv("SELFIT_ASSET_STORE", "local").strip().lower()
    if backend == "oss":
        return OssAssetStore(
            cache_dir,
            _oss_bucket_from_env(),
            prefix=os.getenv("SELFIT_OSS_PREFIX", "selfit/onboarding"),
            public_base_url=os.getenv("SELFIT_OSS_PUBLIC_BASE_URL", ""),
        )
    if backend == "s3":
        client, bucket = _s3_client_from_env()
        return S3AssetStore(
            cache_dir,
            client,
            bucket,
            prefix=os.getenv("SELFIT_S3_PREFIX", "selfit/onboarding"),
            public_base_url=os.getenv("SELFIT_S3_PUBLIC_BASE_URL", ""),
        )
    return LocalAssetStore(cache_dir)

"""验证当前资产配置后端是否可用。

用法：
    python scripts/check_asset_store.py            # 按 .env / 环境变量探测
    python scripts/check_asset_store.py --strict   # 非 local 后端失败时返回非 0

会写入并回读一个探针对象（selfit_assets_probe/ 前缀），不影响真实资产。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from app import selfit_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="非 local 后端失败时返回非 0")
    args = parser.parse_args()

    import os

    backend = os.getenv("SELFIT_ASSET_STORE", "local").strip().lower()
    print(f"asset store backend: {backend}")

    try:
        store = selfit_assets.asset_store_from_env()
    except Exception as exc:
        print(f"[fail] 后端初始化失败: {exc}")
        return 1 if args.strict or backend != "local" else 0

    key = f"selfit_assets_probe/probe_{int(time.time())}.txt"
    payload = f"selfit asset store probe {time.time()}".encode("utf-8")
    try:
        store.save(key, payload, "text/plain")
    except Exception as exc:
        print(f"[fail] 写入探针对象失败: {exc}")
        return 1 if args.strict or backend != "local" else 0

    local_path = store.local_path(key)
    public_url = store.public_url(key)
    print(f"[ok] 写入成功: {key}")
    print(f"  本地缓存: {local_path}")
    if public_url:
        print(f"  公开 URL: {public_url}")
    if backend != "local":
        print("  请到对象存储控制台确认对象已出现（本地缓存成功不代表云端成功时，本脚本已直接报错）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

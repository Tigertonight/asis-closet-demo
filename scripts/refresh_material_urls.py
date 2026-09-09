"""发布素材 ID → 临时 URL 映射，普通项目运行不需要七牛密钥。

    python scripts/refresh_material_urls.py --all
    python scripts/refresh_material_urls.py --expires-in 604800 --refresh-within 86400

默认签发 7 天有效的 URL，仅刷新缺少临时链接、已过期或 24 小时内到期的条目。
由持有 .env.qiniu 的维护者执行，再将更新后的素材 JSON 分发给项目使用者。
不重新上传图片。保留源 URL 供下次刷新，清单不保存签名密钥。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--expires-in", type=int, help="链接有效秒数（默认 604800，即 7 天）")
    parser.add_argument("--refresh-within", type=int, default=86400)
    parser.add_argument("--all", action="store_true", help="刷新全部七牛临时链接")
    args = parser.parse_args()
    registry = MaterialRegistry(args.registry)
    count = registry.refresh_temporary_urls(ttl_seconds=args.expires_in,
                                           within_seconds=args.refresh_within, force=args.all)
    print(f"[ok] 已刷新 {count} 条临时链接：{registry.path}")
    print(f"[info] 更新时间：{datetime.now(timezone.utc).isoformat()}；请同步更新后的素材 JSON。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""把 scripts/data/stylist_context_seed.json 物化为 AI 问答上下文配置。

幂等：按 xhs_uid 合并——已存在的条目不覆盖（管理员在后台改过就以后台为准），
只补缺失的。prompt 不动（保留后台修改）。服务器部署后跑一次即可：

    .venv/bin/python scripts/seed_stylist_context.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stylist_context import (  # noqa: E402
    STYLIST_CONTEXT_CONFIG_PATH,
    load_stylist_context_config,
    write_stylist_context_config,
)

SEED_PATH = ROOT / "scripts" / "data" / "stylist_context_seed.json"


def main() -> None:
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    config = load_stylist_context_config()
    existing_uids = {str(item.get("xhs_uid") or "") for item in config["users"]}
    added = 0
    for user in seed.get("users", []):
        uid = str(user.get("xhs_uid") or "").strip()
        if not uid or uid in existing_uids:
            continue
        config["users"].append(
            {
                "entry_id": f"scu_{uid[:12]}",
                "phone": str(user.get("phone") or ""),
                "xhs_uid": uid,
                "nickname": str(user.get("nickname") or ""),
                "doc": str(user.get("doc") or ""),
                "created_at": "seed",
                "updated_at": "seed",
            }
        )
        existing_uids.add(uid)
        added += 1
    write_stylist_context_config(config)
    print(
        f"stylist context config -> {STYLIST_CONTEXT_CONFIG_PATH}\n"
        f"added {added} entries, total {len(config['users'])} users"
    )


if __name__ == "__main__":
    main()

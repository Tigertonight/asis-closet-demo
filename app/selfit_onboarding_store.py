"""selfit onboarding 元数据存储后端。

现状：默认 `JsonFileStore`（sessions.json）与历史行为完全一致。
可选：`SqliteOnboardingStore`，通过环境变量切换：

    SELFIT_ONBOARDING_STORE_BACKEND=json | sqlite   # 默认 json

设计说明：
- 两个后端共用一个极简契约：`load() -> dict[str, list]` / `save(data)`，
  业务层（selfit_onboarding.py）只认 dict-of-lists，不感知后端差异。
- SQLite 版的价值：单文件事务写入（多请求写入由 SQLite 串行化，避免
  JSON 文件并发覆盖丢数据）、幂等键唯一约束、为后续 Postgres 迁移铺路。
- 已知边界：业务层是"读-改-写"模式，跨请求的整体替换语义下并发写同一
  会话仍然后写覆盖先写；真正的行级并发要等接口下沉为行操作，留待
  Postgres 阶段处理。demo/内测规模下 SQLite 后端已足够。
- 数据资产（用户原图/分享图）不走本模块，由资产层管理，见
  selfit_onboarding.py 顶部注释：资产只增不删。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

STORE_VERSION = 1

# collection -> 文档主键字段
COLLECTIONS = {
    "sessions": "session_id",
    "idempotency": "key",
    "report_jobs": "job_id",
    "reports": "report_id",
    "outfit_requests": "request_id",
    "share_assets": "asset_id",
    "public_report_shares": "share_id",
    # 按用户持久索引最新一张通过校验的 onboarding 照片。
    # 会话过期只清理草稿，不应让 App 丢失用户的试穿形象。
    "user_photos": "user_id",
    # 照片检测被拒的留存记录（asset 只增不删，供算法离线优化阈值）
    "rejected_photos": "record_id",
}


def empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, **{collection: [] for collection in COLLECTIONS}}


class SqliteOnboardingStore:
    """以 (collection, doc_id) 为主键的文档表实现。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    collection TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    doc TEXT NOT NULL,
                    PRIMARY KEY (collection, doc_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def load(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT collection, doc FROM documents ORDER BY rowid"
            ).fetchall()
        data = empty_store()
        for collection, doc in rows:
            if collection not in COLLECTIONS:
                continue
            try:
                parsed = json.loads(doc)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                data[collection].append(parsed)
        return data

    def save(self, data: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            for collection, id_field in COLLECTIONS.items():
                docs = [doc for doc in data.get(collection, []) if isinstance(doc, dict)]
                live_ids: list[str] = []
                for doc in docs:
                    doc_id = str(doc.get(id_field) or "")
                    if not doc_id:
                        continue
                    live_ids.append(doc_id)
                    conn.execute(
                        "INSERT INTO documents (collection, doc_id, doc) VALUES (?, ?, ?) "
                        "ON CONFLICT (collection, doc_id) DO UPDATE SET doc = excluded.doc",
                        (collection, doc_id, json.dumps(doc, ensure_ascii=False)),
                    )
                if live_ids:
                    placeholders = ",".join("?" for _ in live_ids)
                    conn.execute(
                        f"DELETE FROM documents WHERE collection = ? AND doc_id NOT IN ({placeholders})",
                        (collection, *live_ids),
                    )
                else:
                    conn.execute("DELETE FROM documents WHERE collection = ?", (collection,))

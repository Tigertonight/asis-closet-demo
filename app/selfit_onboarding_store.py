"""Record-oriented SQLite storage; JSON remains available for offline compatibility."""
from __future__ import annotations

import json
import sqlite3
import hashlib
import os
from pathlib import Path
from typing import Any

STORE_VERSION = 1

# collection -> 文档主键字段
COLLECTIONS = {
    "user_profiles": "user_id",
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


class StoreConflict(RuntimeError):
    """A record changed since it was read; never overwrite the newer version."""


def select(data, collection, **filters):
    rows = data.get(collection, [])
    if isinstance(rows, RecordCollection):
        return rows.select(**filters)
    return [row for row in rows if all(row.get(k) == v for k, v in filters.items())]


def find(data, collection, **filters):
    return next(iter(select(data, collection, **filters)), None)


class RecordCollection:
    """Request-local identity map. Fetch only requested records; track original revisions."""
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.rows, self.original = {}, {}
        self.complete = False
        self.queried = set()

    def select(self, **filters):
        for key in filters:
            if key not in self.store.FILTERS and key != COLLECTIONS[self.name]:
                raise ValueError(f"Unsupported query field: {key}")
        query = tuple(sorted(filters.items()))
        if not self.complete and query not in self.queried:
            where, values = ["collection = ?"], [self.name]
            for key, value in filters.items():
                column = "doc_id" if key == COLLECTIONS[self.name] else key
                where.append(f"{column} = ?")
                values.append(value)
            with self.store._connect() as conn:
                records = conn.execute("SELECT doc_id, doc, revision FROM documents WHERE " + " AND ".join(where) + " ORDER BY rowid", values).fetchall()
            for key, raw, revision in records:
                if key in self.original:
                    continue
                try:
                    doc = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(doc, dict):
                    continue
                self.original[key] = (revision, raw)
                self.rows[key] = doc
            self.queried.add(query)
            if not filters:
                self.complete = True
        return [row for row in self.rows.values() if all(row.get(k) == v for k, v in filters.items())]

    def append(self, row):
        key = str(row[COLLECTIONS[self.name]])
        if key in self.rows:
            raise ValueError(f"Duplicate {self.name} record")
        self.rows[key] = row

    def remove(self, row):
        self.rows.pop(str(row[COLLECTIONS[self.name]]), None)

    def __iter__(self):
        return iter(self.select())

    def __len__(self):
        return len(self.select())

    def __getitem__(self, index):
        return self.select()[index]

    def __eq__(self, other):
        return self.select() == other


class RecordUnit(dict):
    def __init__(self, store):
        self.collections = {name: RecordCollection(store, name) for name in COLLECTIONS}
        super().__init__(version=STORE_VERSION, **self.collections)


class SqliteOnboardingStore:
    """One document per assessment/job/report, with indexed lookup and optimistic transactions.

    Collection discriminates logical tables; complex answer/report payloads remain
    JSON within ONE row. Reads never materialize other collections, and commits
    update only changed rows with a revision check in one SQLite transaction.
    """
    FILTERS = ("user_id", "session_id", "created_at", "expires_at", "status", "token_hash")

    def __init__(self, path: Path, legacy_json: Path | None = None):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS documents (collection TEXT NOT NULL, doc_id TEXT NOT NULL, doc TEXT NOT NULL, PRIMARY KEY(collection, doc_id))")
            columns = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
            upgraded = "revision" not in columns
            for column in (*self.FILTERS, "revision"):
                if column not in columns:
                    kind = "INTEGER NOT NULL DEFAULT 1" if column == "revision" else "TEXT"
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {kind}")
            conn.execute("CREATE TABLE IF NOT EXISTS store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            if upgraded:
                for key in self.FILTERS:
                    conn.execute(f"UPDATE documents SET {key} = json_extract(doc, '$.{key}') WHERE json_valid(doc)")
            for key in ("user_id", "session_id", "expires_at", "status", "token_hash"):
                conn.execute(f"CREATE INDEX IF NOT EXISTS docs_{key} ON documents(collection, {key}, created_at)")
            self._import_legacy(conn, legacy_json)

    def _connect(self):
        # closing() avoids retaining connections until a later garbage collection.
        return _Connection(self._path)

    def _import_legacy(self, conn, source):
        if conn.execute("SELECT 1 FROM store_metadata WHERE key='migration_complete'").fetchone():
            return
        existing = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        if source and source.exists() and not existing:
            raw = source.read_bytes()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Invalid legacy onboarding store; migration aborted")
            digest = hashlib.sha256(raw).hexdigest()
            backup = source.with_name(source.name + ".pre-sqlite-" + digest[:12] + ".bak")
            if not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            if backup.read_bytes() != raw:
                raise ValueError("Legacy backup verification failed")
            counts = {}
            for name, id_field in COLLECTIONS.items():
                docs = data.get(name, [])
                if not isinstance(docs, list):
                    raise ValueError(f"Invalid legacy collection: {name}")
                for doc in docs:
                    if not isinstance(doc, dict) or not doc.get(id_field):
                        raise ValueError(f"Invalid legacy record in {name}")
                    self._insert(conn, name, str(doc[id_field]), doc)
                counts[name] = len(docs)
                actual = conn.execute("SELECT count(*) FROM documents WHERE collection=?", (name,)).fetchone()[0]
                if actual != len(docs):
                    raise ValueError(f"Migration count mismatch: {name}")
            conn.execute("INSERT INTO store_metadata VALUES ('legacy_import', ?)", (json.dumps({"sha256": digest, "backup": str(backup), "counts": counts}),))
        conn.execute("INSERT INTO store_metadata VALUES ('migration_complete', '1')")

    @staticmethod
    def _encode(doc):
        return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))

    def _insert(self, conn, name, key, doc):
        fields = ",".join(self.FILTERS)
        placeholders = ",".join("?" for _ in self.FILTERS)
        conn.execute(f"INSERT INTO documents(collection,doc_id,doc,{fields}) VALUES (?,?,?,{placeholders})", (name, key, self._encode(doc), *(doc.get(k) for k in self.FILTERS)))

    def load(self):
        return RecordUnit(self)

    def save(self, data):
        if not isinstance(data, RecordUnit):
            # Explicit seed/import callers: insert only, never delete unseen rows.
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for name, id_field in COLLECTIONS.items():
                    for doc in data.get(name, []):
                        self._insert(conn, name, str(doc[id_field]), doc)
            return
        changes = []
        for name, collection in data.collections.items():
            current = data[name]
            if current is collection:
                rows = collection.rows
            else:
                # Legacy list replacement (e.g. explicit deletion) must compare
                # against records actually read, never against the whole database.
                collection.select()
                rows = {str(row[COLLECTIONS[name]]): row for row in current}
            for key in collection.original.keys() | rows.keys():
                old = collection.original.get(key)
                doc = rows.get(key)
                raw = self._encode(doc) if doc is not None else None
                if old is not None and doc is not None and json.loads(old[1]) == doc:
                    continue
                changes.append((name, key, old, doc, raw))
        if not changes:
            return
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for name, key, old, doc, raw in changes:
                if old is None:
                    try:
                        self._insert(conn, name, key, doc)
                    except sqlite3.IntegrityError as exc:
                        raise StoreConflict(f"{name} was concurrently created") from exc
                elif doc is None:
                    if conn.execute("DELETE FROM documents WHERE collection=? AND doc_id=? AND revision=?", (name, key, old[0])).rowcount != 1:
                        raise StoreConflict(f"{name} changed before deletion")
                else:
                    fields = ",".join(f"{k}=?" for k in self.FILTERS)
                    result = conn.execute(f"UPDATE documents SET doc=?, {fields}, revision=revision+1 WHERE collection=? AND doc_id=? AND revision=?", (raw, *(doc.get(k) for k in self.FILTERS), name, key, old[0]))
                    if result.rowcount != 1:
                        raise StoreConflict(f"{name} changed concurrently")
        for name, key, old, doc, raw in changes:
            collection = data.collections[name]
            if doc is None:
                collection.original.pop(key, None)
                collection.rows.pop(key, None)
            else:
                collection.original[key] = ((old[0] + 1) if old else 1, raw)
                collection.rows[key] = doc
        for name, collection in data.collections.items():
            if data[name] is not collection:
                collection.rows = {str(row[COLLECTIONS[name]]): row for row in data[name]}
                data[name] = collection


class _Connection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=10)
        self.conn.execute("PRAGMA busy_timeout=10000")

    def __enter__(self):
        return self.conn

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()

#!/usr/bin/env python3
"""Offline onboarding migration, verification, backup and expiry maintenance."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.selfit_onboarding_store import COLLECTIONS, SqliteOnboardingStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['migrate', 'check', 'export', 'prune'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = args.directory / 'sessions.sqlite3'
    if args.action != 'migrate' and not path.exists():
        parser.error('Database does not exist; migrate first')
    store = SqliteOnboardingStore(path, args.directory / 'sessions.json')
    if args.action == 'export':
        if args.output is None:
            parser.error('--output is required; never overwrite the legacy source')
        with args.output.open('x', encoding='utf-8') as out:
            unit = store.load()
            json.dump({'version': 1, **{name: list(unit[name]) for name in COLLECTIONS}}, out, ensure_ascii=False)
    elif args.action == 'prune':
        # Run outside peak traffic. A concurrent edit aborts the transaction rather
        # than overwriting it; retry the maintenance command from a fresh snapshot.
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        backup = path.with_name(f'sessions.pre-prune-{stamp}.sqlite3')
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        from app.selfit_onboarding import _prune_store
        unit = store.load()
        plain = {'version': 1, **{name: list(unit[name]) for name in COLLECTIONS}}
        cleaned = _prune_store(plain)
        unit.update(cleaned)
        store.save(unit)
        print(json.dumps({'backup': str(backup)}))
    with store._connect() as conn:
        check = conn.execute('PRAGMA integrity_check').fetchone()[0]
        counts = dict(conn.execute('SELECT collection, count(*) FROM documents GROUP BY collection'))
        imported = conn.execute("SELECT value FROM store_metadata WHERE key='legacy_import'").fetchone()
    print(json.dumps({'integrity': check, 'counts': counts, 'migration': json.loads(imported[0]) if imported else None}, ensure_ascii=False))
    if check != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

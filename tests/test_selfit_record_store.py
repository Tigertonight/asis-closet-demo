import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import selfit_onboarding_store as db


def seed(store, **collections):
    store.save({**db.empty_store(), **collections})


def test_json_migration_preserves_every_record_and_is_idempotent(tmp_path):
    source = tmp_path / 'sessions.json'
    legacy = {**db.empty_store(), 'sessions': [{'session_id': 's1', 'user_id': 'u1', 'preferences': {'x': 7}}], 'reports': [{'report_id': 'r1', 'user_id': 'u1', 'data': {'typeId': 'loop'}}]}
    source.write_text(json.dumps(legacy))
    path = tmp_path / 'sessions.sqlite3'
    store = db.SqliteOnboardingStore(path, source)
    assert {key: list(store.load()[key]) for key in db.COLLECTIONS} == {key: legacy[key] for key in db.COLLECTIONS}
    backup = next(tmp_path.glob('*.bak'))
    assert backup.read_bytes() == source.read_bytes()
    data = store.load()
    db.find(data, 'sessions', session_id='s1')['revision'] = 2
    store.save(data)
    restarted = db.SqliteOnboardingStore(path, source)
    assert db.find(restarted.load(), 'sessions', session_id='s1')['revision'] == 2
    assert len(list(tmp_path.glob('*.bak'))) == 1


def test_invalid_migration_rolls_back_without_marking_complete(tmp_path):
    source = tmp_path / 'sessions.json'
    source.write_text(json.dumps({'sessions': [{'session_id': 's1'}, {'session_id': 's1'}]}))
    path = tmp_path / 'sessions.sqlite3'
    with pytest.raises(sqlite3.IntegrityError):
        db.SqliteOnboardingStore(path, source)
    source.write_text(json.dumps({'sessions': [{'session_id': 's1'}]}))
    store = db.SqliteOnboardingStore(path, source)
    assert len(store.load()['sessions']) == 1


def test_lookup_and_save_only_touch_selected_record(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    seed(store, sessions=[{'session_id': f's{i}', 'user_id': f'u{i}'} for i in range(100)], reports=[{'report_id':'r1'}])
    unit = store.load()
    assert all(not c.original for c in unit.collections.values())
    record = db.find(unit, 'sessions', session_id='s42')
    assert list(unit.collections['sessions'].original) == ['s42']
    assert not unit.collections['reports'].original
    record['revision'] = 2
    store.save(unit)
    with sqlite3.connect(store._path) as conn:
        assert conn.execute('SELECT count(*) FROM documents WHERE revision=2').fetchone()[0] == 1
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT doc FROM documents WHERE collection='reports' AND user_id='u1'").fetchall()
        assert any('docs_user_id' in row[-1] for row in plan)


def test_unrelated_concurrent_updates_are_preserved(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    seed(store, sessions=[{'session_id': 'a'}, {'session_id': 'b'}])
    left, right = store.load(), store.load()
    db.find(left, 'sessions', session_id='a')['revision'] = 7
    db.find(right, 'sessions', session_id='b')['revision'] = 9
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(store.save, [left, right]))
    result = store.load()
    assert db.find(result, 'sessions', session_id='a')['revision'] == 7
    assert db.find(result, 'sessions', session_id='b')['revision'] == 9


def test_conflict_rolls_back_other_changes_in_same_commit(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    seed(store, sessions=[{'session_id': 'a', 'revision': 1}])
    left, right = store.load(), store.load()
    db.find(left, 'sessions', session_id='a')['revision'] = 2
    db.find(right, 'sessions', session_id='a')['revision'] = 3
    right['reports'].append({'report_id': 'should_not_exist'})
    store.save(left)
    with pytest.raises(db.StoreConflict):
        store.save(right)
    assert db.find(store.load(), 'sessions', session_id='a')['revision'] == 2
    assert list(store.load()['reports']) == []


def test_deletion_does_not_remove_concurrent_insert(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    seed(store, sessions=[{'session_id': 'a'}])
    old = store.load()
    assert list(old['sessions']) == [{'session_id': 'a'}]
    new = store.load()
    new['sessions'].append({'session_id':'b'})
    store.save(new)
    old['sessions'] = []
    store.save(old)
    assert list(store.load()['sessions']) == [{'session_id':'b'}]


def test_repeated_commit_and_idempotency_replacement(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    unit = store.load()
    unit['idempotency'].append({'key': 'u:k', 'body': {'v': 1}})
    store.save(unit)
    row = db.find(unit, 'idempotency', key='u:k')
    unit['idempotency'].remove(row)
    unit['idempotency'].append({'key': 'u:k', 'body': {'v': 2}})
    store.save(unit)
    assert db.find(store.load(), 'idempotency', key='u:k')['body']['v'] == 2


def test_old_sqlite_schema_is_upgraded_in_place(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE documents(collection TEXT,doc_id TEXT,doc TEXT,PRIMARY KEY(collection,doc_id))')
        conn.execute('INSERT INTO documents VALUES (?,?,?)', ('reports', 'r1', json.dumps({'report_id':'r1','user_id':'u1'})))
    store = db.SqliteOnboardingStore(path)
    assert db.select(store.load(), 'reports', user_id='u1') == [{'report_id':'r1','user_id':'u1'}]


def test_duplicate_workers_build_one_report(monkeypatch, tmp_path):
    import threading
    import time
    from app import selfit_onboarding as onboarding, selfit_report
    monkeypatch.setenv('SELFIT_ONBOARDING_STORE_BACKEND', 'sqlite')
    monkeypatch.setattr(onboarding, 'SELFIT_ONBOARDING_DIR', tmp_path)
    monkeypatch.setattr(onboarding, 'SELFIT_ONBOARDING_STORE_PATH', tmp_path / 'sessions.json')
    store = onboarding._sqlite_store()
    seed(store, sessions=[{'session_id':'s1', 'expires_at':'2099-01-01T00:00:00Z'}], report_jobs=[{'job_id':'j1', 'session_id':'s1', 'status':'queued'}])
    calls = []
    def build(session):
        calls.append(session['session_id'])
        time.sleep(.02)
        return {'typeId':'loop'}
    monkeypatch.setattr(selfit_report, 'build_report', build)
    barrier = threading.Barrier(2)
    original = onboarding._write_store
    def synchronized_save(data):
        # Force both workers to read queued before either can claim the row.
        job = db.find(data, 'report_jobs', job_id='j1')
        if job and job['status'] == 'processing':
            barrier.wait(timeout=5)
        return original(data)
    monkeypatch.setattr(onboarding, '_write_store', synchronized_save)
    with ThreadPoolExecutor(2) as workers:
        list(workers.map(onboarding._run_report_job, ['j1', 'j1']))
    assert calls == ['s1']
    assert len(store.load()['reports']) == 1
    assert db.find(store.load(), 'report_jobs', job_id='j1')['status'] == 'completed'


def test_missing_idempotency_key_remains_a_conflict_after_concurrent_insert(tmp_path):
    store = db.SqliteOnboardingStore(tmp_path / 's.db')
    first, second = store.load(), store.load()
    assert db.find(first, 'idempotency', key='u:k') is None
    assert db.find(second, 'idempotency', key='u:k') is None
    first['idempotency'].append({'key':'u:k', 'body':{'sessionId':'first'}})
    store.save(first)
    # A second lookup during submission cannot silently adopt/overwrite the
    # winner's key and create another assessment under the same idempotency key.
    assert db.find(second, 'idempotency', key='u:k') is None
    second['idempotency'].append({'key':'u:k', 'body':{'sessionId':'second'}})
    second['sessions'].append({'session_id':'second'})
    with pytest.raises(db.StoreConflict):
        store.save(second)
    assert list(store.load()['sessions']) == []

import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app import auth, beta_access, storage, tryon


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(auth, 'AUTH_DIR', tmp_path / 'auth')
    monkeypatch.setenv('SELFIT_TRYON_DAILY_LIMIT', '30')
    class Executor:
        calls = []
        def submit(self, *args): self.calls.append(args)
    executor = Executor()
    monkeypatch.setattr(tryon, 'TRYON_JOB_EXECUTOR', executor)
    buf = io.BytesIO()
    Image.new('RGB', (64, 96), 'pink').save(buf, 'PNG')
    def submit(key='same', user='alice', **kwargs):
        with storage.user_storage(user):
            return tryon.create_outfit_tryon_job(buf.getvalue(), 'photo.png', 'outfit-a', 'standard', '',
                                                user, client_request_id=key, charge_quota=True, **kwargs)
    return executor, submit


def test_parallel_duplicate_submission_generates_and_charges_only_once(runtime, monkeypatch):
    executor, submit = runtime
    monkeypatch.setenv('SELFIT_TRYON_DAILY_LIMIT', '1')
    barrier = threading.Barrier(8)
    def click(_):
        barrier.wait()
        return submit()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(click, range(8)))
    assert len({r['job_id'] for r in results}) == len(executor.calls) == 1
    assert beta_access.tryon_used_today('alice') == 1
    assert submit()['job_id'] == results[0]['job_id'], 'known task remains retrievable at quota limit'
    with pytest.raises(HTTPException) as error: submit('different')
    assert error.value.status_code == 429 and len(executor.calls) == 1


def test_full_queue_rejects_without_charge_and_releases_on_completion(runtime, monkeypatch):
    executor, submit = runtime
    monkeypatch.setattr(tryon, 'TRYON_ADMISSION', threading.BoundedSemaphore(1))
    job = submit()
    with pytest.raises(HTTPException) as error: submit('next', 'bob')
    assert error.value.status_code == 429 and beta_access.tryon_used_today('bob') == 0
    def finish(user, job_id):
        tryon._update_tryon_job(job_id, status='failed', error={'message':'test'})
    monkeypatch.setattr(tryon, '_run_outfit_tryon_job', finish)
    executor.calls[0][0](*executor.calls[0][1:])
    assert submit('next', 'bob')['status'] == 'queued'
    assert beta_access.tryon_used_today('bob') == 1


def test_submit_failure_refunds_quota_and_is_retryable(runtime, monkeypatch):
    executor, submit = runtime
    def fail(*args): raise RuntimeError('executor closed')
    monkeypatch.setattr(executor, 'submit', fail)
    with pytest.raises(HTTPException) as error: submit()
    assert error.value.status_code == 503 and beta_access.tryon_used_today('alice') == 0
    assert tryon.TRYON_ADMISSION.acquire(blocking=False)
    tryon.TRYON_ADMISSION.release()
    job = submit()  # Same request returns its persisted failure, without another attempt.
    assert job['status'] == 'failed' and job['error']['code'] == 'tryon_not_started'
    monkeypatch.setattr(executor, 'submit', lambda *args: executor.calls.append(args))
    with storage.user_storage('alice'):
        retry = tryon.retry_outfit_tryon_job(job['job_id'], 'alice')
    assert retry['attempt'] == 2 and beta_access.tryon_used_today('alice') == 1


def test_parallel_retries_queue_once_and_keep_feedback_without_charging(runtime):
    executor, submit = runtime
    job = submit()
    # Simulate a finished worker returning its permit.
    tryon.TRYON_ADMISSION.release()
    with storage.user_storage('alice'):
        tryon._update_tryon_job(job['job_id'], status='failed', result={'pipeline':{
            'quality_review': {'issues':[{'code':'quality.face_changed'}]}}})
    barrier = threading.Barrier(6)
    def click(_):
        barrier.wait()
        with storage.user_storage('alice'):
            return tryon.retry_outfit_tryon_job(job['job_id'], 'alice')
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(click, range(6)))
    assert len(executor.calls) == 2
    assert all(r['attempt'] == 2 and r['retry_feedback'] == ['quality.face_changed'] for r in results)
    assert beta_access.tryon_used_today('alice') == 1


def test_restart_recovers_dead_jobs_but_never_duplicates_live_work(runtime, monkeypatch):
    _, submit = runtime
    job = submit()
    with storage.user_storage('alice'):
        assert tryon.get_outfit_tryon_job(job['job_id'])['status'] == 'queued'
        tryon._update_tryon_job(job['job_id'], owner_instance='old', owner_pid=987654321)
        def dead(pid, signal): raise ProcessLookupError()
        monkeypatch.setattr(tryon.os, 'kill', dead)
        recovered = tryon.get_outfit_tryon_job(job['job_id'])
        assert recovered['status'] == 'failed' and recovered['error']['code'] == 'tryon_interrupted'
        assert recovered['original_image_path'] == job['original_image_path']
        assert 'owner_pid' not in recovered
        tryon._update_tryon_job(job['job_id'], status='processing', owner_instance='other-live', owner_pid=987654322)
        monkeypatch.setattr(tryon.os, 'kill', lambda *_: None)
        assert tryon.get_outfit_tryon_job(job['job_id'])['status'] == 'processing'
    with storage.user_storage('bob'):
        with pytest.raises(HTTPException) as error: tryon.get_outfit_tryon_job(job['job_id'])
        assert error.value.status_code == 404


def test_legacy_interrupted_job_can_be_retried(runtime):
    _, submit = runtime
    job = submit()
    with storage.user_storage('alice'):
        tryon._update_tryon_job(job['job_id'], owner_instance=None, owner_pid=None,
                                created_at='2020-01-01T00:00:00+00:00')
        assert tryon.get_outfit_tryon_job(job['job_id'])['status'] == 'failed'


def test_preset_bypasses_busy_generation_queue_and_charges_once(runtime, monkeypatch):
    from app import closet, selfit_tryon_presets
    executor, submit = runtime
    monkeypatch.setattr(tryon, 'TRYON_ADMISSION', threading.BoundedSemaphore(1))
    tryon.TRYON_ADMISSION.acquire()
    preset={'example_id':'preset','outfit':{'item_ids':['top']},'quality_review':{},'image_path':'/preset.webp'}
    monkeypatch.setattr(selfit_tryon_presets, 'find_preset', lambda *a: preset)
    records=[]
    monkeypatch.setattr(closet, 'record_selfit_tryon_result', lambda *a: records.append(a))
    for _ in range(2):
        assert submit(wear_all_items=True, model_id='model')['status'] == 'completed'
    assert len(records) == beta_access.tryon_used_today('alice') == 1
    assert not executor.calls


def test_history_snapshot_does_not_change_after_regeneration(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    with storage.user_storage('alice'):
        root=tryon._tryon_output_dir();root.mkdir(parents=True)
        source=root/'result.png';Image.new('RGB',(20,20),'red').save(source)
        result={'status':'generated','result':{'image_path':tryon._public_output_path(source)}}
        first=deepcopy(result);tryon._snapshot_tryon_result({'job_id':'a'*18,'attempt':1}, first)
        saved=tryon._tryon_result_disk_path(first['result']['image_path']);before=saved.read_bytes()
        Image.new('RGB',(20,20),'blue').save(source)
        second=deepcopy(result);tryon._snapshot_tryon_result({'job_id':'a'*18,'attempt':2}, second)
        assert saved.read_bytes() == before != source.read_bytes()
        assert first['result']['image_path'] != second['result']['image_path']


def test_pixel_limit_is_checked_before_decode(monkeypatch):
    class Oversize:
        width=10000; height=10000
        def load(self): pytest.fail('must not decode')
    monkeypatch.setattr(tryon.Image, 'open', lambda *_: Oversize())
    with pytest.raises(HTTPException) as error: tryon._read_upload_image(b'image', 'large.png', 'person')
    assert error.value.status_code == 413


def test_job_preparation_does_not_block_event_loop(monkeypatch):
    import importlib
    main=importlib.import_module('app.main')
    started=threading.Event();release=threading.Event();seen=[]
    def slow(*args, **kwargs):
        seen.append(storage.storage_context().user_id)
        started.set();assert release.wait(3)
        return {'status':'queued'}
    monkeypatch.setattr(main, 'create_outfit_tryon_job', slow)
    async def scenario():
        task=asyncio.create_task(main.selfit_try_on_job_create(
            person_image=UploadFile(filename='x.png',file=io.BytesIO(b'image')),
            outfit_id='a',photo_mode=None,scene_label=None,force_regenerate=False,selected_item_ids=None,
            client_request_id='same',wear_all_items=False,model_id=None,current_user={'user_id':'alice'}))
        try:
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.01)
            assert started.is_set() and not task.done(), 'event loop remains available while image work is pending'
        finally: release.set()
        assert (await task)['status']=='queued'
    asyncio.run(scenario());assert seen==['alice']


def test_burst_is_bounded_to_two_workers_and_four_admitted_jobs(runtime, monkeypatch):
    _, submit = runtime
    release = threading.Event()
    lock = threading.Lock()
    active = peak = 0
    def work(user, job_id):
        nonlocal active, peak
        with lock:
            active += 1; peak = max(peak, active)
        try:
            assert release.wait(5)
            tryon._update_tryon_job(job_id, status='completed')
        finally:
            with lock: active -= 1
    monkeypatch.setattr(tryon, '_run_outfit_tryon_job', work)
    with ThreadPoolExecutor(max_workers=2) as workers:
        monkeypatch.setattr(tryon, 'TRYON_JOB_EXECUTOR', workers)
        def request(index):
            try:
                return submit('burst', f'user-{index}')['job_id']
            except HTTPException as error:
                assert error.status_code == 429
                return None
        try:
            with ThreadPoolExecutor(max_workers=24) as clients:
                results = list(clients.map(request, range(24)))
            assert sum(bool(r) for r in results) == 4
            assert sum(beta_access.tryon_used_today(f'user-{i}') for i in range(24)) == 4
            assert peak == 2
        finally:
            release.set()
    assert active == 0
    for _ in range(4): assert tryon.TRYON_ADMISSION.acquire(blocking=False)
    for _ in range(4): tryon.TRYON_ADMISSION.release()


def test_quota_refund_uses_original_day_and_preserves_other_admissions(monkeypatch):
    original = beta_access._today_key()
    with pytest.raises(RuntimeError):
        with beta_access.reserve_tryon_quota('alice'):
            beta_access.consume_tryon_quota('alice')
            monkeypatch.setattr(beta_access, '_today_key', lambda: '2099-01-01')
            beta_access.consume_tryon_quota('alice')
            raise RuntimeError('submission failed after midnight')
    assert beta_access._load_usage()['alice'] == {original: 1, '2099-01-01': 1}


def test_unexpected_worker_failure_is_visible_and_frees_capacity(runtime, monkeypatch):
    executor, submit = runtime
    job = submit()
    def crash(*args): raise RuntimeError('worker crashed')
    monkeypatch.setattr(tryon, '_run_outfit_tryon_job', crash)
    executor.calls[0][0](*executor.calls[0][1:])
    with storage.user_storage('alice'):
        failed = tryon.get_outfit_tryon_job(job['job_id'])
    assert failed['status'] == 'failed' and failed['error']['code'] == 'tryon_worker_failed'
    for _ in range(4): assert tryon.TRYON_ADMISSION.acquire(blocking=False)
    for _ in range(4): tryon.TRYON_ADMISSION.release()


def test_legacy_upload_does_not_block_and_cancellation_retains_capacity(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    budget = threading.BoundedSemaphore(1)
    monkeypatch.setattr(tryon, 'TRYON_ADMISSION', budget)
    started = threading.Event(); release = threading.Event(); finished = threading.Event()
    buf = io.BytesIO(); Image.new('RGB', (20, 20), 'white').save(buf, 'PNG')
    seen = []
    def generate(person, garment):
        seen.append(storage.storage_context().user_id)
        started.set()
        try:
            assert release.wait(5)
            return {'status':'generated'}
        finally: finished.set()
    monkeypatch.setattr(tryon, 'run_try_on', generate)
    def upload(): return UploadFile(filename='photo.png', file=io.BytesIO(buf.getvalue()))
    async def scenario():
        with storage.user_storage('legacy'):
            task = asyncio.create_task(tryon.run_try_on_upload(upload(), upload()))
            try:
                for _ in range(100):
                    if started.is_set(): break
                    await asyncio.sleep(.01)
                assert started.is_set() and not task.done()
                task.cancel()
                with pytest.raises(asyncio.CancelledError): await task
                assert not budget.acquire(blocking=False), 'disconnection cannot oversubscribe the pool'
                with pytest.raises(HTTPException) as error:
                    await tryon.run_try_on_upload(upload(), upload())
                assert error.value.status_code == 429
            finally: release.set()
            for _ in range(100):
                if finished.is_set(): break
                await asyncio.sleep(.01)
    with ThreadPoolExecutor(max_workers=2) as workers:
        monkeypatch.setattr(tryon, 'TRYON_JOB_EXECUTOR', workers)
        asyncio.run(scenario())
    assert seen == ['legacy'] and budget.acquire(blocking=False)
    budget.release()


def test_legacy_invalid_upload_returns_capacity(monkeypatch):
    budget = threading.BoundedSemaphore(1)
    monkeypatch.setattr(tryon, 'TRYON_ADMISSION', budget)
    async def scenario():
        for content, status in [(b'', 400), (b'invalid', 400), (b'x'*(tryon.MAX_IMAGE_BYTES+1), 413)]:
            upload = UploadFile(filename='bad.png', file=io.BytesIO(content))
            with pytest.raises(HTTPException) as error:
                await tryon._run_uploaded_tryon([(upload,'person')], lambda *_:pytest.fail('invalid input must not generate'))
            assert error.value.status_code == status
            assert budget.acquire(blocking=False)
            budget.release()
    asyncio.run(scenario())


def test_concurrent_successes_and_regeneration_remain_in_history(monkeypatch, tmp_path):
    from app import closet
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(closet, 'get_outfit', lambda *_: {'title':'Test outfit'})
    def save(index):
        result = {'status':'generated', 'tryon_id':'same-photo-and-outfit',
                  'result':{'image_path':f'/user-assets/tryon/job-results/{index}.png'}}
        with storage.user_storage('alice'):
            return closet.record_selfit_tryon_result('outfit', result)
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(save, range(8)))
    assert len({r['record_id'] for r in records}) == 8
    assert save(0)['record_id'] == records[0]['record_id']
    with storage.user_storage('alice'):
        assert closet.list_tryon_records()['total'] == 8

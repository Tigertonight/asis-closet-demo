import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageDraw

from app import closet, closet_image_worker as worker


def test_small_accessory_triggers_fallback_but_failed_worker_is_bounded(monkeypatch):
    image = Image.new('RGB', (600, 600), (207, 66, 171))
    ImageDraw.Draw(image).rectangle((240, 240, 359, 359), fill='black')
    keyed = closet._remove_uniform_chroma_background(image)
    assert keyed is not None
    assert not closet._has_meaningful_transparency(keyed)  # the incident's <6% condition
    calls = []
    monkeypatch.setattr(worker.sys, 'platform', 'linux')
    monkeypatch.setattr(worker, '_memory_available', lambda: True)
    monkeypatch.setattr(closet.RembgMattingProvider, 'available', lambda _: True)
    def failure(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], -9)
    monkeypatch.setattr(worker.subprocess, 'run', failure)
    with worker.fallback_budget():
        for _ in range(3):
            result, status = closet._ensure_transparent_ai_cutout(image)
            assert status == 'opaque_rejected'
    assert len(calls) == 1  # no cascade of retries/models after a resource failure


def test_timeout_reaps_real_child_and_releases_slot(monkeypatch, tmp_path):
    original_run = subprocess.run
    child = tmp_path / 'pid'
    monkeypatch.setattr(worker.sys, 'platform', 'linux')
    monkeypatch.setattr(worker, '_memory_available', lambda: True)
    monkeypatch.setattr(worker, 'TIMEOUT_SECONDS', .3)
    def slow(*args, **kwargs):
        code = f"import os,time;open({str(child)!r},'w').write(str(os.getpid()));time.sleep(20)"
        return original_run([sys.executable, '-c', code], **kwargs)
    monkeypatch.setattr(worker.subprocess, 'run', slow)
    with worker.fallback_budget():
        assert worker.run_image_worker(Image.new('RGB', (10, 10)), 'matte') is None
    pid = int(child.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert worker._SLOT.acquire(blocking=False)
    worker._SLOT.release()


def test_oversized_upload_rejected_before_decode(monkeypatch):
    image = Image.new('RGB', (20, 20))
    data = io.BytesIO(); image.save(data, 'PNG')
    monkeypatch.setattr(closet, 'MAX_IMPORT_PIXELS', 100)
    with pytest.raises(HTTPException) as exc:
        closet._save_source_image(data.getvalue(), 'large.png', 'upload')
    assert exc.value.status_code == 413


def test_full_queue_rejects_before_read(monkeypatch):
    monkeypatch.setattr(closet, 'IMPORT_ADMISSION', threading.BoundedSemaphore(1))
    closet.IMPORT_ADMISSION.acquire()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(closet.create_import_upload_job([], 'test'))
    assert exc.value.status_code == 429


def test_validation_failure_returns_admission_slot(monkeypatch):
    monkeypatch.setattr(closet, 'IMPORT_ADMISSION', threading.BoundedSemaphore(1))
    with pytest.raises(HTTPException):
        asyncio.run(closet.create_import_upload_job([], 'test'))
    assert closet.IMPORT_ADMISSION.acquire(blocking=False)


def test_interrupted_job_becomes_retryable_but_live_worker_is_untouched(monkeypatch):
    writes = []
    monkeypatch.setattr(closet, '_write_import_job', lambda j: writes.append(dict(j)))
    old = dict(job_id='a'*18, status='processing', created_at='2026-01-01T00:00:00+00:00')
    recovered = closet._recover_interrupted_import(old)
    assert recovered['status'] == 'failed'
    assert recovered['error']['code'] == 'import_interrupted'
    active = dict(job_id='b'*18, status='processing', owner_instance=closet.IMPORT_PROCESS_ID)
    assert closet._recover_interrupted_import(active)['status'] == 'processing'
    assert len(writes) == 1


def test_resource_failure_keeps_successful_inventory_items(monkeypatch, tmp_path):
    provider = closet.AIGarmentCutoutProvider()
    monkeypatch.setattr(provider, '_provider_kind', lambda: 'test')
    candidates = [{'category':'top','confidence':.9,'bbox':[0,0,1,1]},
                  {'category':'accessory','confidence':.9,'bbox':[0,0,1,1]}]
    monkeypatch.setattr(provider, '_analyze_inventory', lambda _: candidates)
    monkeypatch.setattr(closet, '_save_inventory_candidate_crop', lambda *a: tmp_path/'crop.png')
    good = Image.new('RGBA',(100,100),(0,0,0,0));ImageDraw.Draw(good).rectangle((20,20,80,80),fill='red')
    bad = Image.new('RGBA',(100,100),'white')
    images = iter([good,bad])
    monkeypatch.setattr(provider, '_generate_cutout', lambda *a: next(images))
    monkeypatch.setattr(closet.RembgMattingProvider, 'remove_background', lambda *a: None)
    monkeypatch.setattr(closet, '_closet_item_from_ai_cutout', lambda **kw: {'item_id':'kept','pipeline':{}})
    monkeypatch.setattr(closet, '_public_closet_path', lambda p: str(p))
    items = provider.extract_inventory({'image':good}, tmp_path)
    assert [i['item_id'] for i in items] == ['kept']
    assert provider.last_attempt['status'] == 'partial'
    assert provider.last_attempt['failures'][0]['index'] == 1


def test_low_memory_skips_worker_without_starting_model(monkeypatch):
    monkeypatch.setattr(worker.sys, 'platform', 'linux')
    monkeypatch.setattr(worker, '_memory_available', lambda: False)
    monkeypatch.setattr(worker.subprocess, 'run', lambda *a, **k: pytest.fail('must not start'))
    with worker.fallback_budget():
        assert worker.run_image_worker(Image.new('RGB',(10,10)), 'matte') is None


def test_successful_worker_is_decoded_and_budget_resets(monkeypatch):
    monkeypatch.setattr(worker.sys, 'platform', 'linux')
    monkeypatch.setattr(worker, '_memory_available', lambda: True)
    calls = []
    def success(command, **kwargs):
        calls.append(command)
        Image.new('RGBA',(12,12),(255,0,0,128)).save(command[4])
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(worker.subprocess, 'run', success)
    for _ in range(2):
        with worker.fallback_budget():
            result = worker.run_image_worker(Image.new('RGB',(10,10)), 'matte')
            assert result.getpixel((0,0)) == (255,0,0,128)
    assert len(calls) == 2


def test_legacy_retry_recovers_and_submits_only_once(monkeypatch):
    job = dict(job_id='a'*18, status='processing', created_at='2026-01-01T00:00:00+00:00', sources=[])
    monkeypatch.setattr(closet, '_read_import_job', lambda _: dict(job))
    monkeypatch.setattr(closet, '_write_import_job', lambda j: job.update(j))
    monkeypatch.setattr(closet, 'IMPORT_ADMISSION', threading.BoundedSemaphore(1))
    class Executor:
        calls = []
        def submit(self, *args): self.calls.append(args)
    executor = Executor()
    monkeypatch.setattr(closet, 'IMPORT_JOB_EXECUTOR', executor)
    assert closet.retry_import_job('a'*18, 'test')['status'] == 'queued'
    assert closet.retry_import_job('a'*18, 'test')['status'] == 'queued'
    assert len(executor.calls) == 1


def test_submission_failure_marks_task_retryable_and_releases_slot(monkeypatch):
    job = dict(job_id='a'*18, status='failed', sources=[])
    monkeypatch.setattr(closet, '_read_import_job', lambda _: dict(job))
    monkeypatch.setattr(closet, '_write_import_job', lambda j: job.update(j))
    monkeypatch.setattr(closet, 'IMPORT_ADMISSION', threading.BoundedSemaphore(1))
    class Executor:
        def submit(self, *args): raise RuntimeError('executor shut down')
    monkeypatch.setattr(closet, 'IMPORT_JOB_EXECUTOR', Executor())
    with pytest.raises(RuntimeError):
        closet.retry_import_job('a'*18, 'test')
    assert job['status'] == 'failed'
    assert job['error']['code'] == 'import_not_started'
    assert closet.IMPORT_ADMISSION.acquire(blocking=False)

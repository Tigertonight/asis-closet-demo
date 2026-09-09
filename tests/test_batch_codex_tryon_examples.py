"""Regression checks for batch bookkeeping, isolation, and result provenance."""
import json
from pathlib import Path

import pytest

from scripts import batch_codex_tryon_examples as batch


def test_initialization_builds_exact_cross_product_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, 'BATCH', tmp_path)
    for model in batch.MODELS:
        records = batch.initialize(model)
        assert len(records) == 80
        assert all(r['modelId'] == model for p, r in records)
    paths = list(tmp_path.glob('*/*/job.json'))
    assert len(paths) == 240
    rows = [json.loads(p.read_text()) for p in paths]
    assert len({r['id'] for r in rows}) == 240
    assert len({r['outfitId'] for r in rows}) == 80
    first = paths[0]
    row = json.loads(first.read_text())
    row['status'] = 'pending'
    first.write_text(json.dumps(row))
    batch.initialize(row['modelId'])
    assert json.loads(first.read_text())['status'] == 'pending'


def test_resume_refuses_changed_model(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, 'BATCH', tmp_path)
    path, row = batch.initialize('female_slim_1')[0]
    row['model']['sha256'] = 'wrong'
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='source changed'):
        batch.initialize('female_slim_1')


def test_ingest_rejects_wrong_stage_before_copy(tmp_path):
    path = tmp_path / 'job.json'
    record = {'requestPath': 'stage_1_visible_clothing/codex_request.json'}
    with pytest.raises(ValueError, match='Wrong stage'):
        batch.ingest(path, record, 'stage_2_visible_accessories', tmp_path / 'absent.png')
    assert not (tmp_path / 'codex_result.png').exists()


def test_publish_does_not_mark_pending_examples_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, 'BATCH', tmp_path / 'batch')
    monkeypatch.setattr(batch, 'INDEX', tmp_path / 'examples.json')
    for model in batch.MODELS:
        batch.initialize(model)
    batch.publish(False)
    data = json.loads(batch.INDEX.read_text())
    assert data['status'] == 'in_progress'
    assert data['counts'] == {'expected': 240, 'records': 240, 'outfits': 80, 'models': 3,
                              'generated': 0, 'uploaded': 0, 'failed': 0, 'failedImages': 0,
                              'failedUploaded': 0, 'blocked': 0, 'pending': 240,
                              'totalImages': 0, 'totalUploaded': 0, 'processed': 0}
    assert all('result' not in r for r in data['examples'])
    # Existing Xiaohongshu source links may contain xsec_token; storage download
    # authorization has the distinct query key token and must never be saved.
    assert '?token=' not in batch.INDEX.read_text()
    assert '&token=' not in batch.INDEX.read_text()


def test_quality_failure_keeps_actual_output_without_claiming_success(monkeypatch, tmp_path):
    from PIL import Image
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    base = tmp_path / 'example'
    stage = base / 'pipeline' / 'run' / 'stage_2_visible_accessories'
    stage.mkdir(parents=True)
    source = stage / 'codex_result.png'
    Image.new('RGB', (2, 2), 'white').save(source)
    stage.joinpath('codex_result.receipt.json').write_text(json.dumps({'sha256': batch.digest(source)}))
    record = {'status': 'failed', 'workDir': 'example/pipeline/run'}
    finalized = batch.finalize_failure(base / 'job.json', record)
    assert finalized['status'] == 'failed_quality'
    assert finalized['usable'] is False
    assert 'result' not in finalized
    assert finalized['failedResult']['qualityPassed'] is False
    assert (tmp_path / finalized['failedResult']['localPath']).read_bytes() == source.read_bytes()
    assert batch.upload_receipt_path(tmp_path / finalized['failedResult']['localPath']).name == 'quality-failed.upload.json'
    with pytest.raises(ValueError, match='Only a failed'):
        batch.finalize_failure(base / 'job.json', finalized)

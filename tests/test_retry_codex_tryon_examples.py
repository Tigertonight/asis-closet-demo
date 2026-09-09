import json
from pathlib import Path

import pytest

from scripts import retry_codex_tryon_examples as retry


def test_claim_prevents_a_second_generation_call(monkeypatch, tmp_path):
    monkeypatch.setattr(retry, 'ROOT', tmp_path)
    case = tmp_path / 'case'
    stage = case / 'pipeline' / 'stage_2_visible_accessories'
    stage.mkdir(parents=True)
    request = stage / 'codex_request.json'
    request.write_text(json.dumps({'requestId': 'same-input-request'}))
    row = {'status': 'pending', 'requestPath': str(request.relative_to(tmp_path))}
    assert retry.claim(case / 'job.json', row) == request
    with pytest.raises(FileExistsError):
        retry.claim(case / 'job.json', row)
    retry.finish_claim(case / 'job.json', stage.name, 'received')
    with pytest.raises(FileExistsError):
        retry.claim(case / 'job.json', row)


def test_no_image_retry_keeps_previous_real_image_and_records_rejection(monkeypatch, tmp_path):
    base = tmp_path / 'batch'
    current = base / 'round'
    current.mkdir(parents=True)
    monkeypatch.setattr(retry, 'ROOT', tmp_path)
    monkeypatch.setattr(retry, 'ORIGINAL_BATCH', base)
    monkeypatch.setattr(retry, 'ROUND_ID', 'retry-round-02')
    monkeypatch.setattr(retry, 'ROUND', current)
    monkeypatch.setattr(retry, 'MANIFEST', current / 'manifest.json')
    monkeypatch.setattr(retry, 'ROUND_INDEX', current / 'examples.json')
    monkeypatch.setattr(retry.batch, 'BATCH', base)
    monkeypatch.setattr(retry.batch, 'INDEX', tmp_path / 'main.json')
    original = base / 'model' / 'look' / 'quality-failed.png'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'original-image-is-preserved')
    previous = {'id': 'model--look', 'modelId': 'model', 'key': 'look', 'status': 'failed_quality',
                'failedResult': {'localPath': str(original.relative_to(tmp_path)), 'sha256': 'original'},
                'usable': False, 'retryHistory': [{'roundId': 'retry-round-01', 'retained': True}]}
    candidate = {'id': previous['id'], 'modelId': 'model', 'key': 'look',
                 'status': 'blocked_moderation', 'toolError': {'code': 'moderation_blocked', 'requestId': 'new-rejection'}}
    (current / 'baseline-index.json').write_text(json.dumps({'examples': [previous]}))
    retry.MANIFEST.write_text(json.dumps({'expected': 1}))
    def publish(upload=False, report=False):
        if retry.batch.BATCH == current:
            retry.ROUND_INDEX.write_text(json.dumps({'examples': [candidate], 'counts': {
                'expected': 240, 'records': 1, 'uploaded': 0, 'failedUploaded': 0,
                'failedImages': 0, 'blocked': 1}}))
    monkeypatch.setattr(retry.batch, 'publish', publish)
    summary = retry.publish(False)
    result = json.loads((original.parent / 'job.json').read_text())
    assert result['status'] == 'failed_quality'
    assert result['failedResult'] == previous['failedResult']
    assert original.read_bytes() == b'original-image-is-preserved'
    assert result['latestRetry']['status'] == 'blocked_moderation'
    assert result['retryHistory'][0] == previous['retryHistory'][0]
    assert result['retryHistory'][1]['promoted'] is False
    assert result['retryHistory'][1]['attempt']['toolError']['requestId'] == 'new-rejection'
    assert summary['status'] == 'completed_with_issues'
    retry.publish(False)
    assert len(json.loads((original.parent / 'job.json').read_text())['retryHistory']) == 2


def test_error_cannot_overwrite_a_completed_success(tmp_path):
    path = tmp_path / 'job.json'
    row = {'status': 'generated_local', 'result': {'localPath': 'real-result.png'}}
    path.write_text(json.dumps(row))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='pending request'):
        retry.record_error(path, row, {'code': 'moderation_blocked', 'requestId': 'tool-id'})
    assert path.read_bytes() == before
    assert row['status'] == 'generated_local'


def test_blocked_only_round_preserves_previous_stage_and_freezes_selection(monkeypatch, tmp_path):
    base = tmp_path / 'batch'
    current = base / 'retry-round-02'
    source = tmp_path / 'app/data/styling-delivery.v1.json'
    source.parent.mkdir(parents=True)
    source.write_text('{}')
    base.mkdir()
    (base / 'styling-delivery.snapshot.json').write_text('{}')
    (base / 'input-snapshot.json').write_text('{}')
    model = tmp_path / 'model.png'
    model.write_bytes(b'unchanged-model')
    old_work = base / 'retry-round-01/model/look/pipeline/id'
    clothing = old_work / 'stage_1_visible_clothing'
    accessories = old_work / 'stage_2_visible_accessories'
    clothing.mkdir(parents=True)
    accessories.mkdir()
    (clothing / 'codex_result.png').write_bytes(b'valid-prior-clothing')
    (clothing / 'codex_result.receipt.json').write_text('{}')
    request = accessories / 'codex_request.json'
    request.write_text('{}')
    blocked = {'id': 'model--look', 'modelId': 'model', 'key': 'look',
               'status': 'blocked_moderation', 'workDir': str(old_work.relative_to(tmp_path)),
               'requestPath': str(request.relative_to(tmp_path)),
               'model': {'localPath': 'model.png', 'sha256': retry.batch.digest(model)},
               'retryHistory': [{'roundId': 'retry-round-01'}],
               'latestRetry': {'roundId': 'retry-round-01'}}
    index = tmp_path / 'main.json'
    index.write_text(json.dumps({'examples': [blocked, {
        'id': 'quality-failure-excluded', 'status': 'failed_quality'}]}))
    for key, value in {'ROOT': tmp_path, 'ORIGINAL_BATCH': base,
                       'ORIGINAL_INDEX': index, 'ROUND_ID': 'retry-round-02',
                       'ROUND': current, 'MANIFEST': current / 'manifest.json',
                       'ROUND_INDEX': current / 'examples.json'}.items():
        monkeypatch.setattr(retry, key, value)
    retry.initialize(only_blocked=True)
    # Resuming without the flag must use the already-frozen selection.
    retry.initialize()
    manifest = json.loads(retry.MANIFEST.read_text())
    assert manifest['expected'] == 1
    assert manifest['targetStatuses'] == ['blocked_moderation']
    assert manifest['targets'][0]['retryStage'] == 'stage_2_visible_accessories'
    path, row = retry.selected()[0]
    assert row['retryHistory'] == blocked['retryHistory']
    assert 'latestRetry' not in row
    assert (path.parent / 'pipeline/id/stage_1_visible_clothing/codex_result.png').read_bytes() == b'valid-prior-clothing'
    assert (clothing / 'codex_result.png').read_bytes() == b'valid-prior-clothing'
    assert json.loads((current / 'baseline-index.json').read_text())['examples'][0] == blocked

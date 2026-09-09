"""One additional, non-destructive attempt for each failed example.

The built-in image_gen tool remains the only generator. Each stage may be claimed
once in this round. A passed failed-stage retry may proceed to a later stage once;
another quality failure or tool rejection ends that example's retry.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import write_json_atomic
from scripts import batch_codex_tryon_examples as batch

ORIGINAL_BATCH = batch.BATCH
ORIGINAL_INDEX = batch.INDEX
ROUND_ID = 'retry-round-01'
ROUND = ORIGINAL_BATCH / ROUND_ID
MANIFEST = ROUND / 'manifest.json'
ROUND_INDEX = ROUND / 'examples.json'
TERMINAL = {'generated_local', 'uploaded', 'failed_quality', 'blocked_moderation', 'error'}


def read(path):
    return json.loads(Path(path).read_text())


def configure_round(round_id):
    if not re.fullmatch(r'retry-round-[0-9]{2,}', round_id):
        raise ValueError('Round must have the form retry-round-02')
    global ROUND_ID, ROUND, MANIFEST, ROUND_INDEX
    ROUND_ID = round_id
    ROUND = ORIGINAL_BATCH / round_id
    MANIFEST = ROUND / 'manifest.json'
    ROUND_INDEX = ROUND / 'examples.json'


def initialize(only_blocked=False):
    if batch.digest(ROOT / 'app/data/styling-delivery.v1.json') != batch.digest(ORIGINAL_BATCH / 'styling-delivery.snapshot.json'):
        raise ValueError('Delivery changed since baseline; do not mix different inputs in this retry round')
    ROUND.mkdir(parents=True, exist_ok=True)
    baseline_path = ROUND / 'baseline-index.json'
    if not baseline_path.exists():
        shutil.copyfile(ORIGINAL_INDEX, baseline_path)
    baseline = read(baseline_path)
    statuses = ['blocked_moderation'] if only_blocked else ['failed_quality', 'blocked_moderation']
    if MANIFEST.exists():
        statuses = read(MANIFEST).get('targetStatuses', ['failed_quality', 'blocked_moderation'])
    targets = [r for r in baseline['examples'] if r['status'] in statuses]
    if not MANIFEST.exists():
        write_json_atomic(MANIFEST, {'roundId': ROUND_ID, 'createdAt': batch.now(),
            'baselineIndex': str(baseline_path.relative_to(ROOT)), 'expected': len(targets),
            'targetStatuses': statuses,
            'policy': 'one additional attempt at the failed stage; later required stages once; no further retries',
            'targets': [{'id': r['id'], 'modelId': r['modelId'], 'key': r['key'],
                         'previousStatus': r['status'],
                         'retryStage': r['failedResult']['lastGeneratedStage'] if r.get('failedResult')
                         else Path(r['requestPath']).parent.name} for r in targets]})
    manifest = read(MANIFEST)
    assert {r['id'] for r in targets} == {r['id'] for r in manifest['targets']}
    target_map = {r['id']: r for r in manifest['targets']}
    for previous in targets:
        if batch.digest(ROOT / previous['model']['localPath']) != previous['model']['sha256']:
            raise ValueError('Model input changed since baseline')
        target = target_map[previous['id']]
        case = ROUND / previous['modelId'] / previous['key']
        if (case / 'job.json').exists():
            continue
        old_work = ROOT / previous['workDir']
        work = case / 'pipeline' / old_work.name
        if work.exists():
            # Only an incomplete new-round staging copy can exist without job.json.
            shutil.rmtree(work)
        shutil.copytree(old_work, work, ignore=shutil.ignore_patterns('*.previous'))
        for stage in work.glob('stage_*'):
            if stage.name >= target['retryStage']:
                for filename in ('codex_result.png', 'codex_result.receipt.json'):
                    stage.joinpath(filename).unlink(missing_ok=True)
        record = deepcopy(previous)
        for field in ('result', 'failedResult', 'requestPath', 'pipelineStatus', 'qualityReview',
                      'imageEdit', 'semanticReview', 'visualReview', 'toolError', 'externalError',
                      'generationError', 'generationErrors', 'usable', 'reusedFrom', 'attemptArchives', 'latestRetry'):
            record.pop(field, None)
        record.update(status='queued', updatedAt=batch.now(), artifactDir=str(case.relative_to(ROOT)),
                      workDir=str(work.relative_to(ROOT)),
                      retryRound={**target, 'roundId': ROUND_ID, 'maxAttemptsPerStage': 1,
                                  'baselineIndex': str(baseline_path.relative_to(ROOT))})
        write_json_atomic(case / 'job.json', record)
    shutil.copyfile(ORIGINAL_BATCH / 'input-snapshot.json', ROUND / 'input-snapshot.json')
    for name in ('completion-summary.json', 'verification.json'):
        backup = ROUND / ('baseline-' + name)
        if not backup.exists() and (ORIGINAL_BATCH / name).exists():
            shutil.copyfile(ORIGINAL_BATCH / name, backup)
    print(json.dumps({'roundId': ROUND_ID, 'targets': len(targets)}))


def selected(model=None, key=None):
    result = []
    for target in read(MANIFEST)['targets']:
        if model and target['modelId'] != model or key and target['key'] != key:
            continue
        path = ROUND / target['modelId'] / target['key'] / 'job.json'
        result.append((path, read(path)))
    return result


def claim(path, row):
    if row['status'] != 'pending' or not row.get('requestPath'):
        raise ValueError('Only a pending generation request can be claimed')
    request_path = ROOT / row['requestPath']
    request = read(request_path)
    claim_path = path.parent / 'generation-attempts' / (request_path.parent.name + '.json')
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents a second call after interruption or resumption.
    with claim_path.open('x') as stream:
        json.dump({'requestId': request['requestId'], 'requestPath': row['requestPath'],
                   'status': 'started', 'claimedAt': batch.now(), 'attempt': 1}, stream, indent=2)
    return request_path


def finish_claim(path, stage, status):
    claim_path = path.parent / 'generation-attempts' / (stage + '.json')
    data = read(claim_path)
    data.update(status=status, finishedAt=batch.now())
    write_json_atomic(claim_path, data)


def active_claim(path, row, stage=None):
    if row['status'] != 'pending' or not row.get('requestPath') or row.get('result') or row.get('failedResult'):
        raise ValueError('Only an uncompleted pending request can accept a tool outcome')
    request_path = ROOT / row['requestPath']
    if stage and stage != request_path.parent.name:
        raise ValueError('Wrong stage for active claim')
    data = read(path.parent / 'generation-attempts' / (request_path.parent.name + '.json'))
    if data['status'] != 'started' or data['requestId'] != read(request_path)['requestId']:
        raise ValueError('No matching single-attempt claim')
    return request_path


def record_error(path, row, error):
    request_path = active_claim(path, row)
    if not isinstance(error, dict) or not error.get('code'):
        raise ValueError('A structured real tool error is required')
    if error['code'] == 'moderation_blocked' and not error.get('requestId'):
        raise ValueError('Moderation rejection must retain its service request ID')
    row.update(status='blocked_moderation' if error['code'] == 'moderation_blocked' else 'error',
               toolError=error, updatedAt=batch.now())
    write_json_atomic(path, row)
    finish_claim(path, request_path.parent.name, 'tool_error')
    return row


def compact(row):
    keys = ('id', 'status', 'artifactDir', 'workDir', 'requestPath', 'result', 'failedResult',
            'toolError', 'externalError', 'generationError', 'qualityReview', 'semanticReview')
    return {k: deepcopy(row[k]) for k in keys if k in row}


@contextmanager
def retry_publisher():
    old_batch, old_index = batch.BATCH, batch.INDEX
    batch.BATCH, batch.INDEX = ROUND, ROUND_INDEX
    try:
        yield
    finally:
        batch.BATCH, batch.INDEX = old_batch, old_index


def publish(upload=False, report=True):
    manifest = read(MANIFEST)
    with retry_publisher():
        batch.publish(upload=upload, report=False)
    payload = read(ROUND_INDEX)
    rows = payload['examples']
    counts = payload['counts']
    counts['expected'] = manifest['expected']
    counts['errors'] = sum(r['status'] == 'error' for r in rows)
    counts['processed'] = counts['uploaded'] + counts['failedUploaded'] + counts['blocked'] + counts['errors']
    done = counts['processed'] == counts['expected']
    payload.update(batchId=ROUND_ID, status='completed_with_issues' if done and
                   counts['failedImages'] + counts['blocked'] + counts['errors'] else 'complete' if done else 'in_progress')
    write_json_atomic(ROUND_INDEX, payload)
    old_rows = {r['id']: r for r in read(ROUND / 'baseline-index.json')['examples']}
    for row in rows:
        if row['status'] not in TERMINAL:
            continue
        new_image = row.get('result') or row.get('failedResult')
        if new_image and not new_image.get('verified'):
            continue
        previous = old_rows[row['id']]
        # A new real image becomes current; a no-image rejection preserves any
        # previously available image while recording the latest failed attempt.
        promote = bool(new_image) or (not (previous.get('result') or previous.get('failedResult'))
                                     and row['status'] == 'blocked_moderation')
        current = deepcopy(row if promote else previous)
        if current['status'] == 'uploaded':
            current['status'] = 'generated_local'
        entry = {'roundId': ROUND_ID, 'baselineIndex': str((ROUND / 'baseline-index.json').relative_to(ROOT)),
                 'recordPath': str((ROUND / row['modelId'] / row['key'] / 'job.json').relative_to(ROOT)),
                 'previous': compact(previous), 'attempt': compact(row), 'promoted': promote,
                 'maxAttemptsPerStage': 1}
        current['retryHistory'] = [r for r in previous.get('retryHistory', []) if r['roundId'] != ROUND_ID] + [entry]
        current['latestRetry'] = {'roundId': ROUND_ID, 'status': row['status'], 'recordPath': entry['recordPath']}
        write_json_atomic(ORIGINAL_BATCH / row['modelId'] / row['key'] / 'job.json', current)
    summary = {'roundId': ROUND_ID, 'status': payload['status'], 'updatedAt': batch.now(), 'counts': counts,
               'baselineIndex': str((ROUND / 'baseline-index.json').relative_to(ROOT)),
               'index': str(ROUND_INDEX.relative_to(ROOT)), 'maxAttemptsPerStage': 1}
    write_json_atomic(ROUND / 'summary.json', summary)
    rounds_path = ORIGINAL_BATCH / 'retry-rounds.json'
    rounds = read(rounds_path) if rounds_path.exists() else []
    write_json_atomic(rounds_path, [r for r in rounds if r['roundId'] != ROUND_ID] + [summary])
    batch.publish(upload=False, report=False)
    if report:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def verify():
    manifest = read(MANIFEST)
    baseline = {r['id']: r for r in read(ROUND / 'baseline-index.json')['examples']}
    rows = {r['id']: (p, r) for p, r in selected()}
    errors, claims_checked, old_images_checked = [], 0, 0
    if set(rows) != {r['id'] for r in manifest['targets']}:
        errors.append({'id': 'matrix', 'error': 'Retry target matrix differs from baseline failures'})
    for old in baseline.values():
        result = old.get('result') or old.get('failedResult')
        if result:
            if batch.digest(ROOT / result['localPath']) != result['sha256']:
                errors.append({'id': old['id'], 'error': 'Previous image was overwritten'})
            else:
                old_images_checked += 1
    completed = 0
    for target in manifest['targets']:
        path, row = rows[target['id']]
        if row['status'] not in TERMINAL:
            continue
        completed += 1
        try:
            work = ROOT / row['workDir']
            old_work = ROOT / baseline[row['id']]['workDir']
            initial = read(work / target['retryStage'] / 'codex_request.json')
            old_initial = read(old_work / target['retryStage'] / 'codex_request.json')
            if initial['requestId'] != old_initial['requestId']:
                raise ValueError('Retry changed the original failed-stage prompt or references')
            expected_claims = {target['retryStage']}
            claims = sorted(path.parent.glob('generation-attempts/*.json'))
            if len(claims) not in ({1, 2} if target['retryStage'] == 'stage_1_visible_clothing' else {1}):
                raise ValueError('Unexpected additional stage attempts')
            if len(claims) == 2:
                expected_claims.add('stage_2_visible_accessories')
            if {p.stem for p in claims} != expected_claims:
                raise ValueError('Missing failed-stage claim or unexpected stage')
            for claim_path in claims:
                data = read(claim_path)
                request_path = work / claim_path.stem / 'codex_request.json'
                request = read(request_path)
                digest = hashlib.sha256(request['prompt'].encode())
                for ref in request['referenced_image_paths']:
                    digest.update(Path(ref).read_bytes())
                if data['attempt'] != 1 or data['requestId'] != request['requestId'] or digest.hexdigest() != request['requestId']:
                    raise ValueError('Stage claim or request provenance mismatch')
                if data['status'] == 'received':
                    receipt = read(request_path.with_name('codex_result.receipt.json'))
                    if receipt['requestId'] != request['requestId'] or receipt['sha256'] != batch.digest(request_path.with_name('codex_result.png')):
                        raise ValueError('Received output receipt mismatch')
                elif data['status'] == 'tool_error':
                    if row['status'] not in {'blocked_moderation', 'error'} or not row.get('toolError'):
                        raise ValueError('Missing tool error for claimed failed call')
                else:
                    raise ValueError('Completed example still has an unfinished stage claim')
                claims_checked += 1
        except (ValueError, KeyError, OSError, TypeError) as exc:
            errors.append({'id': row['id'], 'error': str(exc)})
    report = {'roundId': ROUND_ID, 'verifiedAt': batch.now(), 'expected': manifest['expected'],
              'completed': completed, 'claimsVerified': claims_checked,
              'previousImagesUnchanged': old_images_checked, 'errors': errors,
              'complete': completed == manifest['expected'] and not errors}
    write_json_atomic(ROUND / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'prepare', 'claim', 'ingest', 'finalize-failure',
                                           'record-error', 'status', 'publish', 'watch', 'verify'))
    parser.add_argument('--model', choices=batch.MODELS)
    parser.add_argument('--key')
    parser.add_argument('--stage')
    parser.add_argument('--result', type=Path)
    parser.add_argument('--error-file', type=Path)
    parser.add_argument('--limit', type=int, default=4)
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--round', default='retry-round-01', dest='round_id')
    parser.add_argument('--only-blocked', action='store_true', help='At init, select only moderation-blocked cases')
    args = parser.parse_args()
    configure_round(args.round_id)
    if args.command == 'init':
        initialize(only_blocked=args.only_blocked)
        return publish(False)
    if args.command == 'publish':
        return publish(args.upload)
    if args.command == 'verify':
        return verify()
    if args.command == 'watch':
        failures, previous = 0, None
        while True:
            try:
                summary = publish(True, report=False)
                failures = 0
                if summary['counts'] != previous:
                    print(json.dumps(summary, ensure_ascii=False), flush=True)
                    previous = summary['counts']
                if summary['status'] != 'in_progress':
                    return
            except Exception as exc:
                failures += 1
                print(json.dumps({'uploadErrorType': type(exc).__name__, 'consecutiveErrors': failures}), flush=True)
                if failures >= 5:
                    raise SystemExit('Retry uploader stopped after five failures')
            time.sleep(30)
    rows = selected(args.model, args.key)
    if args.command == 'status':
        from collections import Counter
        print(json.dumps(dict(Counter(r['status'] for _, r in rows))))
        return
    if not args.model:
        raise ValueError('--model is required')
    if args.command == 'prepare':
        rows = [(p, r) for p, r in rows if r['status'] in {'queued', 'pending'}][:args.limit]
        output = []
        for path, row in rows:
            row = batch.advance(path, row)
            output.append({'key': row['key'], 'status': row['status'], 'requestPath': row.get('requestPath')})
        print(json.dumps(output))
        return
    if not args.key or len(rows) != 1:
        raise ValueError('Exactly one --key is required')
    path, row = rows[0]
    if args.command == 'claim':
        print(str(claim(path, row)))
        return
    if args.command == 'ingest':
        if not args.stage or not args.result:
            raise ValueError('--stage and --result are required')
        active_claim(path, row, args.stage)
        row = batch.ingest(path, row, args.stage, args.result)
        finish_claim(path, args.stage, 'received')
    elif args.command == 'finalize-failure':
        row = batch.finalize_failure(path, row)
    elif args.command == 'record-error':
        if not args.error_file:
            raise ValueError('--error-file is required')
        row = record_error(path, row, read(args.error_file))
    print(json.dumps({'id': row['id'], 'status': row['status'], 'requestPath': row.get('requestPath'),
                      'result': row.get('result'), 'failedResult': row.get('failedResult')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

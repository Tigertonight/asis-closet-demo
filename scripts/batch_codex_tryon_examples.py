"""Resumable 80-outfit × 3-model replay of the real staged try-on pipeline.

Image generation is performed by the Codex built-in image_gen tool. This CLI only
prepares exact requests, imports tool outputs, runs quality checks, and publishes.
Each model owns an isolated directory; only the coordinator calls publish.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import tryon
from app.material_assets import MaterialRegistry, asset_content_url, asset_id_for_bytes, material_download_url, material_source_url, write_json_atomic
from app.storage import storage_context
from app.styling_catalog import delivery_looks, delivered_tryon_plan, outfit_id
from scripts.test_codex_tryon_effect import CodexEffectProvider

BATCH = ROOT / 'outputs/tryon-examples/20260909'
INDEX = ROOT / 'app/data/tryon-examples.v1.json'
MODEL_DIR = ROOT / 'tests/fixtures/tryon_models'
MODELS = {Path(x['file']).stem: x for x in json.loads((MODEL_DIR / 'manifest.json').read_text())['items']
          if x['gender'] == 'female' and x.get('active', True)}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def initialize(model):
    result = []
    for look in delivery_looks():
        binding = look['note_binding']
        key = binding['templateId'] + '--' + binding['noteId']
        path = BATCH / model / key / 'job.json'
        person = MODEL_DIR / MODELS[model]['file']
        oid = outfit_id(look)
        if path.exists():
            record = json.loads(path.read_text())
            if record['outfitId'] != oid or record['model']['sha256'] != digest(person):
                raise ValueError('Batch source changed: start a new version before resuming')
        else:
            record = {'id': model + '--' + key, 'modelId': model, 'key': key, 'outfitId': oid,
                      'noteBinding': binding, 'sourceAssetId': look['source_asset']['assetId'],
                      'itemCount': len(look['items']), 'itemIds': [x['item_id'] for x in look['items']],
                      'model': {**MODELS[model], 'localPath': str(person.relative_to(ROOT)), 'sha256': digest(person)},
                      'provider': CodexEffectProvider.mode, 'strategy': 'visible_clothing_then_accessories',
                      'status': 'queued', 'createdAt': now(), 'updatedAt': now()}
            write_json_atomic(path, record)
        result.append((path, record))
    return result


def advance(path, record):
    base = path.parent
    ctx = replace(storage_context('tryon_examples_' + record['modelId']),
                  upload_dir=base / 'inputs', tryon_output_dir=base / 'pipeline')
    plan, _ = delivered_tryon_plan(record['outfitId'], 'standard', '')
    semantic = tryon._stage('warn', 0, {'provider': 'codex_visual_review_pending', 'verified': False},
                           [tryon._issue('semantic.manual_review_required', '需要检查单品细节', '请核对原图与试穿结果。')])
    with patch.object(tryon, 'storage_context', return_value=ctx), patch.object(tryon, '_review_outfit_semantics', return_value=semantic):
        person_path = ROOT / record['model']['localPath']
        person = tryon._read_upload_image(person_path.read_bytes(), person_path.name, 'person')
        outcome = tryon.run_try_on_from_outfit_plan(person, plan, provider=CodexEffectProvider(),
                                                   force_regenerate=True, wear_all_items=True)
    work = ctx.tryon_output_dir / outcome['tryon_id']
    write_json_atomic(base / 'pipeline-result.json', outcome)
    record.update(status=outcome['status'], workDir=str(work.relative_to(ROOT)), updatedAt=now(),
                  pipelineStatus=outcome['status'], qualityReview=outcome['pipeline']['quality_review'],
                  imageEdit=outcome['pipeline']['image_edit'])
    record.pop('requestPath', None)
    pending = [p for p in sorted(work.glob('stage_*/codex_request.json'))
               if not p.with_name('codex_result.receipt.json').exists()]
    if outcome['status'] == 'pending' and pending:
        record['requestPath'] = str(pending[0].relative_to(ROOT))
    final = outcome['pipeline']['image_edit'].get('evidence', {}).get('result_path')
    if outcome['status'] in {'generated', 'review'} and final:
        target = base / 'result.png'
        shutil.copyfile(final, target)
        with Image.open(target) as im:
            dimensions = list(im.size)
        record.update(status='generated_local', result={'localPath': str(target.relative_to(ROOT)),
                      'sha256': digest(target), 'bytes': target.stat().st_size, 'dimensions': dimensions},
                      semanticReview={'status': 'pending', 'verified': False})
    write_json_atomic(path, record)
    return record


def ingest(path, record, stage, source):
    request_path = ROOT / record['requestPath']
    if request_path.parent.name != stage:
        raise ValueError('Wrong stage for pending request')
    request = json.loads(request_path.read_text())
    source = source.resolve()
    with Image.open(source) as im:
        im.verify()
    target = Path(request['target_path'])
    if not target.resolve().is_relative_to(path.parent.resolve()):
        raise ValueError('Output outside this example')
    if target.exists():
        raise ValueError('Result already exists; use retry to archive it first')
    shutil.copyfile(source, target)
    write_json_atomic(target.with_name('codex_result.receipt.json'),
                      {'requestId': request['requestId'], 'sha256': digest(target),
                       'tool': 'image_gen', 'sourcePath': str(source), 'ingestedAt': now()})
    return advance(path, record)


def reuse_medium_seed():
    path, record = next((p, r) for p, r in initialize('female_medium_1') if r['key'] == 'bolt--outfits-01')
    if record['status'] in {'generated_local', 'uploaded'}:
        return
    old = ROOT / 'outputs/users/codex_effect_test_20260909/tryon/7fbe4b568c5c8f5b'
    if not old.exists():
        return
    for stage in ('stage_1_visible_clothing', 'stage_2_visible_accessories'):
        record = advance(path, record)
        if 'requestPath' not in record:
            break
        request = json.loads((ROOT / record['requestPath']).read_text())
        receipt = json.loads((old / stage / 'codex_result.receipt.json').read_text())
        source = old / stage / 'codex_result.png'
        if request['requestId'] != receipt['requestId'] or digest(source) != receipt['sha256']:
            raise ValueError('Seed inputs differ; do not silently reuse')
        record = ingest(path, record, stage, source)
    record['reusedFrom'] = str(old.relative_to(ROOT))
    write_json_atomic(path, record)


def finalize_failure(path, record):
    """Keep a failed test's actual image without bypassing any quality gate."""
    if record['status'] != 'failed':
        raise ValueError('Only a failed pipeline result can be finalized as quality failure')
    work = ROOT / record['workDir']
    sources = sorted(work.glob('stage_*/codex_result.png'))
    if not sources:
        raise ValueError('No generated image exists for this failed test')
    source = sources[-1]
    receipt = json.loads(source.with_name('codex_result.receipt.json').read_text())
    if receipt['sha256'] != digest(source):
        raise ValueError('Failed output receipt mismatch')
    target = path.parent / 'quality-failed.png'
    shutil.copyfile(source, target)
    with Image.open(target) as im:
        dimensions = list(im.size)
        im.verify()
    record.update(status='failed_quality', updatedAt=now(), usable=False,
                  failedResult={'localPath': str(target.relative_to(ROOT)), 'sha256': digest(target),
                                'bytes': target.stat().st_size, 'dimensions': dimensions,
                                'lastGeneratedStage': source.parent.name, 'completedStages': len(sources),
                                'qualityPassed': False})
    write_json_atomic(path, record)
    return record


def upload_receipt_path(source):
    return source.with_name('upload.json' if source.name == 'result.png' else source.stem + '.upload.json')


def publish(upload=False, report=True):
    import httpx
    from dotenv import load_dotenv
    from scripts.qiniu_material_upload import qiniu_client_from_env
    all_rows = [json.loads(p.read_text()) for p in sorted(BATCH.glob('*/*/job.json'))]
    if len({r['id'] for r in all_rows}) != len(all_rows):
        raise ValueError('Duplicate example IDs')
    registry = MaterialRegistry()
    if upload:
        load_dotenv(ROOT / '.env.qiniu', override=False)
        client = qiniu_client_from_env(os.environ['QINIU_BUCKET'])
        for row in all_rows:
            result = row.get('result') or row.get('failedResult')
            if not result:
                continue
            source = ROOT / result['localPath']
            if not source.resolve().is_relative_to(BATCH.resolve()) or source.suffix.lower() != '.png':
                raise ValueError('Refusing to upload a path outside this image batch')
            raw = source.read_bytes()
            if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Refusing to upload a non-PNG result')
            if hashlib.sha256(raw).hexdigest() != result['sha256']:
                raise ValueError('Final image changed after validation')
            asset_id = asset_id_for_bytes(raw)
            receipt_path = upload_receipt_path(source)
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if receipt.get('assetId') == asset_id and receipt.get('verified'):
                    continue
            key = 'selfit/tryon-examples/20260909/' + asset_id + '.png'
            url = os.environ['QINIU_PUBLIC_BASE'].rstrip('/') + '/' + key
            try:
                uploaded = material_source_url(registry.get(asset_id)) == url
            except KeyError:
                uploaded = False
            storage = client.storage_metadata(key)
            if not uploaded:
                client.put_object(Bucket=client.bucket, Key=key, Body=raw, ContentType='image/png')
                registry.register(raw, url, 'image/png', storage=storage)
            response = httpx.get(material_download_url(registry.get(asset_id)), timeout=60, follow_redirects=False)
            if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != result['sha256']:
                raise RuntimeError('Uploaded image download verification failed: ' + row['id'])
            write_json_atomic(receipt_path, {'assetId': asset_id, 'url': url,
                              'contentUrl': asset_content_url(asset_id), 'storage': storage,
                              'verified': True, 'verifiedAt': now(), 'sha256': result['sha256']})
            print('uploaded ' + row['id'], flush=True)
    for row in all_rows:
        artifact_dir = ROOT / row['artifactDir'] if row.get('artifactDir') else BATCH / row['modelId'] / row['key']
        visual_path = artifact_dir / 'visual-review.json'
        archives = sorted(visual_path.parent.glob('attempts/*/job.json'))
        if archives:
            row['attemptArchives'] = [str(p.parent.relative_to(ROOT)) for p in archives]
        if visual_path.is_file():
            row['visualReview'] = json.loads(visual_path.read_text())
        errors_path = visual_path.with_name('generation-errors.json')
        if errors_path.is_file():
            history = json.loads(errors_path.read_text())
            row['generationErrors'] = history if isinstance(history, list) else [history]
        if row['status'].startswith('blocked'):
            row['toolError'] = row.get('toolError') or row.get('externalError') or row.get('generationError')
        field = 'result' if 'result' in row else 'failedResult'
        if field not in row:
            continue
        source = ROOT / row[field]['localPath']
        receipt_path = upload_receipt_path(source)
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text())
            if receipt['sha256'] != row[field]['sha256']:
                raise ValueError('Stale upload receipt')
            row[field].update(receipt)
            if field == 'result':
                row['status'] = 'uploaded'
    counts = {'expected': 240, 'records': len(all_rows), 'outfits': len({r['outfitId'] for r in all_rows}),
              'models': len({r['modelId'] for r in all_rows}),
              'generated': sum('result' in r for r in all_rows),
              'uploaded': sum(r['status'] == 'uploaded' for r in all_rows),
              'failed': sum(r['status'] in {'failed', 'failed_quality', 'needs_retake', 'error'} for r in all_rows),
              'failedImages': sum('failedResult' in r for r in all_rows),
              'failedUploaded': sum(r.get('failedResult', {}).get('verified', False) for r in all_rows),
              'blocked': sum(r['status'].startswith('blocked') for r in all_rows),
              'pending': sum(r['status'] in {'queued', 'pending'} for r in all_rows)}
    counts.update(totalImages=counts['generated'] + counts['failedImages'],
                  totalUploaded=counts['uploaded'] + counts['failedUploaded'],
                  processed=counts['uploaded'] + counts['failedUploaded'] + counts['blocked'])
    status = ('complete' if counts['uploaded'] == 240 else
              'completed_with_issues' if counts['uploaded'] + counts['failedUploaded'] + counts['blocked'] == 240 else
              'in_progress')
    payload = {'schemaVersion': '1.0', 'batchId': 'styling-80-female-3-20260909',
               'status': status,
               'updatedAt': now(), 'counts': counts, 'examples': all_rows,
               'notes': ['Codex image_gen replay of actual outfit pipeline; only nonempty configured clothing/accessory groups generate stages.',
                         'Geometric quality gates retained; semantic review is explicitly pending unless reviewed.',
                         'failedResult holds real quality-failed outputs for evaluation and is never a passed example.',
                         'Private Qiniu URLs use material contentUrl; expiring access tokens are never persisted.']}
    snapshot_path = BATCH / 'input-snapshot.json'
    if snapshot_path.is_file():
        payload['sourceSnapshot'] = json.loads(snapshot_path.read_text())
    retry_rounds_path = BATCH / 'retry-rounds.json'
    if retry_rounds_path.is_file():
        payload['retryRounds'] = json.loads(retry_rounds_path.read_text())
        payload['retryInProgress'] = any(r['status'] == 'in_progress' for r in payload['retryRounds'])
    write_json_atomic(INDEX, payload)
    if report:
        print(json.dumps(counts))
    return counts


def verify():
    """Audit the entire matrix and completed bytes against exact stage requests."""
    rows = [json.loads(p.read_text()) for p in sorted(BATCH.glob('*/*/job.json'))]
    snapshot_path = BATCH / 'styling-delivery.snapshot.json'
    looks = json.loads(snapshot_path.read_text())['looks'] if snapshot_path.is_file() else delivery_looks()
    expected = {(model, outfit_id(look)) for model in MODELS for look in looks}
    actual = {(r['modelId'], r['outfitId']) for r in rows}
    errors = []
    if actual != expected or len(rows) != len(expected):
        errors.append({'id': 'matrix', 'error': 'Outfit/model matrix differs from current delivery'})
    verified = 0
    uploaded = 0
    verified_failed = 0
    uploaded_failed = 0
    seen_results = {}
    for row in rows:
        if row['status'].startswith('blocked'):
            error = row.get('toolError') or row.get('externalError') or row.get('generationError') or {}
            if (row['status'] != 'blocked_moderation' or error.get('code') != 'moderation_blocked'
                    or not error.get('requestId') or not (ROOT / row.get('requestPath', '__missing__')).is_file()
                    or 'result' in row or 'failedResult' in row):
                errors.append({'id': row['id'], 'error': 'Blocked test lacks a recorded tool rejection or contains a fabricated final result'})
            continue
        field = 'result' if 'result' in row else 'failedResult'
        if field not in row:
            continue
        try:
            result = row[field]
            final = ROOT / result['localPath']
            if digest(ROOT / row['model']['localPath']) != row['model']['sha256']:
                raise ValueError('Model input changed')
            if digest(final) != result['sha256']:
                raise ValueError('Final image hash mismatch')
            if result['sha256'] in seen_results:
                raise ValueError('Same final image reused for distinct combinations')
            seen_results[result['sha256']] = row['id']
            with Image.open(final) as im:
                if list(im.size) != result['dimensions']:
                    raise ValueError('Final image dimensions mismatch')
                if field == 'result' and im.size != (row['model']['width'], row['model']['height']):
                    raise ValueError('Passed image changed dimensions')
                im.verify()
            if field == 'result' and (row['imageEdit']['status'] != 'pass' or row['qualityReview']['status'] == 'fail'):
                raise ValueError('Final image did not pass geometric checks')
            if field == 'failedResult' and (row['status'] != 'failed_quality' or result['qualityPassed'] is not False):
                raise ValueError('Failed output was incorrectly marked as passed')
            requests = sorted((ROOT / row['workDir']).glob('stage_*/codex_request.json'))
            if field == 'failedResult':
                requests = [p for p in requests if p.with_name('codex_result.receipt.json').is_file()
                            and p.with_name('codex_result.png').is_file()]
            if not requests:
                raise ValueError('Missing generation requests')
            if field == 'result':
                artifact_dir = ROOT / row['artifactDir'] if row.get('artifactDir') else BATCH / row['modelId'] / row['key']
                pipeline_path = artifact_dir / 'pipeline-result.json'
                applied_plan = json.loads(pipeline_path.read_text())['applied_outfit_plan']
                expected_stages = [f'stage_{i + 1}_{name}' for i, (name, _) in
                                   enumerate(tryon._outfit_generation_groups(applied_plan))]
                if [p.parent.name for p in requests] != expected_stages:
                    raise ValueError('Passed example did not complete all configured generation stages')
            if digest(requests[-1].with_name('codex_result.png')) != result['sha256']:
                raise ValueError('Final image differs from the last generated stage')
            if field == 'failedResult' and (
                    result['lastGeneratedStage'] != requests[-1].parent.name
                    or result['completedStages'] != len(requests)):
                raise ValueError('Failed example stage metadata differs from actual outputs')
            for path in requests:
                request = json.loads(path.read_text())
                provenance = hashlib.sha256(request['prompt'].encode())
                for source in request['referenced_image_paths']:
                    provenance.update(Path(source).read_bytes())
                receipt = json.loads(path.with_name('codex_result.receipt.json').read_text())
                if provenance.hexdigest() != request['requestId'] or receipt['requestId'] != request['requestId']:
                    raise ValueError('Request provenance mismatch')
                if digest(path.with_name('codex_result.png')) != receipt['sha256']:
                    raise ValueError('Stage image hash mismatch')
            upload_path = upload_receipt_path(final)
            if upload_path.exists():
                upload = json.loads(upload_path.read_text())
                registered = MaterialRegistry().get(upload['assetId'])
                if not upload['verified'] or upload['sha256'] != result['sha256'] or registered['sha256'] != result['sha256']:
                    raise ValueError('Upload receipt mismatch')
                if upload['url'] != registered['url'] or upload['storage'] != registered['storage']:
                    raise ValueError('Upload registry mismatch')
                if field == 'result':
                    uploaded += 1
                else:
                    uploaded_failed += 1
            if field == 'result':
                verified += 1
            else:
                verified_failed += 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'id': row['id'], 'error': str(exc)})
    report = {'verifiedAt': now(), 'expected': len(expected), 'records': len(rows),
              'verifiedLocal': verified, 'verifiedUploaded': uploaded, 'errors': errors,
              'verifiedFailedLocal': verified_failed, 'verifiedFailedUploaded': uploaded_failed,
              'blocked': sum(r['status'].startswith('blocked') for r in rows),
              'allCasesProcessed': not errors and uploaded + uploaded_failed + sum(r['status'].startswith('blocked') for r in rows) == len(expected),
              'complete': not errors and verified == uploaded == len(expected)}
    write_json_atomic(BATCH / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'prepare', 'ingest', 'retry', 'finalize-failure', 'status', 'publish', 'watch', 'verify', 'reuse-seed'))
    parser.add_argument('--model', choices=MODELS)
    parser.add_argument('--key')
    parser.add_argument('--stage')
    parser.add_argument('--result', type=Path)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--upload', action='store_true')
    args = parser.parse_args()
    if args.command == 'verify':
        return verify()
    if args.command == 'watch':
        import importlib
        import time
        publisher = importlib.import_module('scripts.batch_codex_tryon_examples')
        script_stamp = Path(__file__).stat().st_mtime_ns
        previous = None
        errors = 0
        while not (BATCH / 'stop-upload-watcher').exists():
            try:
                updated_stamp = Path(__file__).stat().st_mtime_ns
                if updated_stamp != script_stamp:
                    publisher = importlib.reload(publisher)
                    script_stamp = updated_stamp
                counts = publisher.publish(True, report=False)
                errors = 0
                if counts != previous:
                    print(json.dumps(counts), flush=True)
                    previous = counts
                if counts['uploaded'] + counts['failedUploaded'] + counts['blocked'] == counts['expected']:
                    return
            except Exception as exc:
                errors += 1
                # Network exceptions can contain signed URLs; do not log them.
                print(json.dumps({'uploadErrorType': type(exc).__name__, 'consecutiveErrors': errors}), flush=True)
                if errors >= 5:
                    raise SystemExit('Upload watcher stopped after five consecutive failures')
            time.sleep(30)
        return
    if args.command == 'publish':
        return publish(args.upload)
    if args.command == 'reuse-seed':
        return reuse_medium_seed()
    records = [row for model in ([args.model] if args.model else MODELS) for row in initialize(model)]
    if args.command == 'init':
        print(json.dumps({'initialized': len(records)}))
        return
    if args.command == 'status':
        from collections import Counter
        print(json.dumps(dict(Counter(r['status'] for p, r in records))))
        return
    if not args.model:
        raise ValueError('--model is required for worker operations')
    selected = [(p, r) for p, r in records if not args.key or r['key'] == args.key]
    output = []
    if args.command == 'prepare':
        selected = [(p, r) for p, r in selected if r['status'] in {'queued', 'pending'}][:args.limit]
        for path, record in selected:
            record = advance(path, record)
            output.append({'key': record['key'], 'status': record['status'],
                           'requestPath': str(ROOT / record['requestPath']) if record.get('requestPath') else None})
    else:
        if not args.key or len(selected) != 1:
            raise ValueError('Provide one --key')
        path, record = selected[0]
        if args.command == 'ingest':
            if not args.result or not args.stage:
                raise ValueError('ingest requires --result and --stage')
            record = ingest(path, record, args.stage, args.result)
        elif args.command == 'finalize-failure':
            record = finalize_failure(path, record)
        elif args.command == 'retry':
            if not args.stage or not args.stage.startswith('stage_') or '/' in args.stage:
                raise ValueError('retry requires a stage name')
            work = ROOT / record['workDir']
            archive = path.parent / 'attempts' / datetime.now().strftime('%Y%m%d%H%M%S%f')
            archive.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(path, archive / 'job.json')
            prior_pipeline = path.parent / 'pipeline-result.json'
            if prior_pipeline.exists():
                shutil.copyfile(prior_pipeline, archive / 'pipeline-result.json')
            for stage_dir in sorted(work.glob('stage_*')):
                if stage_dir.name >= args.stage:
                    shutil.copytree(stage_dir, archive / stage_dir.name)
                    for name in ('codex_result.png', 'codex_result.receipt.json'):
                        f = stage_dir / name
                        if f.exists():
                            f.rename(f.with_name(f.name + '.' + datetime.now().strftime('%Y%m%d%H%M%S') + '.previous'))
            record.pop('result', None)
            record.pop('failedResult', None)
            record = advance(path, record)
        output.append({'key': record['key'], 'status': record['status'],
                       'requestPath': str(ROOT / record['requestPath']) if record.get('requestPath') else None,
                       'result': record.get('result')})
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

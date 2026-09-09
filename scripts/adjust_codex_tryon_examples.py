"""Explicitly covered, standing-pose outfit variants for four blocked examples.

Uses the built-in image_gen tool through the existing import/receipt workflow.
Original requests, data, outcomes and quality thresholds are preserved. These
variants change wearing instructions and use one complete-outfit generation pass.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import tryon
from app.material_assets import MaterialRegistry, write_json_atomic
from scripts import batch_codex_tryon_examples as batch
from scripts import retry_codex_tryon_examples as retry
from scripts.test_codex_tryon_effect import CodexEffectProvider

BASE = batch.BATCH
VARIANT_ID = 'prompt-adjusted-01'
VARIANT = BASE / VARIANT_ID
INDEX = VARIANT / 'examples.json'
MANIFEST = VARIANT / 'manifest.json'
MAIN_INDEX = batch.INDEX
STAGE = 'stage_1_complete_outfit'


def read(path):
    return json.loads(Path(path).read_text())


class AdjustedProvider(CodexEffectProvider):
    mode = 'codex_builtin_imagegen_covered_outfit_variant'


def adjusted_plan(original, template):
    plan = deepcopy(original)
    plan['title'] += ' · 日常外穿调整版'
    plan['style_brief'] = '成人站姿日常服装目录照片；按下列调整后的穿法一次完成整套，保留原模特姿势和完整衣着覆盖。'
    changes = ['整套服装和配饰一次生成，保留原人物站姿。', '仅使用简洁单品穿法，消除坐姿、台阶摆包与站姿约束冲突。']
    for item in plan['items']:
        slot = item['slot']
        name = item['category_label']
        wearing = item.get('wearing_instruction', '')
        if template == 'flou':
            if slot == 'top':
                wearing = '保留薄荷绿花卉蕾丝纹样和细肩带；加入同色完整不透内衬，作为日常外穿上衣，胸部和躯干始终由布料遮盖，下摆衔接高腰裤。'
                changes.append('蕾丝上衣增加同色完整不透内衬；这属于服装覆盖调整。')
            elif slot == 'bottom':
                wearing = '薄荷绿高腰长阔腿裤完整穿好；保持两条裤管闭合和自然垂落，裤脚到鞋面，依原站姿形成褶皱。'
            elif slot == 'socks':
                wearing = '米色带蓝色蝴蝶结的袜层穿在长裤里面，仅在裤脚和鞋之间自然可见；不要卷起、开衩或撩起裤腿展示袜子。'
            elif slot == 'shoes':
                wearing = '黑色尖头平底鞋正常穿在双脚，与原站姿一致。'
            elif slot == 'hat':
                wearing = '黑色海军帽正常戴在头顶，帽檐不遮住眼睛和面部。'
            elif slot == 'bag':
                wearing = '白色珍珠球形包以金色链条自然挂在身体一侧前臂，手臂保持原位置，包不悬空。'
            else:
                wearing = '白色立体花朵蕾丝头纱固定于帽子后侧，轻垂到肩后，不遮盖面部，也不替代上衣的完整内衬。'
        elif template == 'loop-curvy':
            if slot == 'top':
                wearing = '白色褶皱上衣使用不透明面料，完整覆盖胸部和躯干，下摆与高腰裙相接，不露内衣。'
            elif slot == 'outer':
                wearing = '黑色短款机车夹克敞开穿在白色上衣外，保留领口、拉链和皮质纹理。'
            elif slot == 'skirt':
                wearing = '保留浅蓝斜襟和交叠边缘；裙身不透明、前后完整闭合，裙摆到大腿中段，正常站立时保持充分覆盖。'
                changes.append('裙摆调整到大腿中段，交叠处完整闭合。')
            elif slot == 'socks':
                item['category_label'] = '黑色不透连裤袜（覆盖调整版）'
                wearing = '使用均匀黑色哑光不透明连裤袜，腰部在裙内，从裙摆下连续覆盖到双脚，不出现内衣边缘。'
                changes.append('原透肤袜改为黑色不透明袜层。')
            elif slot == 'bag':
                wearing = '棕色撞线软质肩包挂在模特右肩，肩带贴合肩膀，包身靠身体右侧；保留原站姿，不加入台阶。'
            elif slot == 'shoes':
                wearing = '黑色搭扣玛丽珍鞋正常穿在连裤袜外，双脚位置与原图一致。'
            elif '眼镜' in name:
                wearing = '细金属框眼镜由模特自然持在身侧，保持手和手臂原位置，不戴在脸上。'
            elif '耳' in name:
                wearing = '金色小圈耳饰正常佩戴在可见耳垂，允许长发自然遮挡部分耳饰。'
            elif '戒指' in name:
                wearing = '金色细戒指佩戴于手指，保持手指原形状。'
            elif '项链' in name:
                wearing = '金色细链绕颈正常佩戴，方形吊坠自然垂落。'
        else:
            raise ValueError('Unconfigured adjusted outfit')
        item['wearing_instruction'] = wearing
        # Preserve the original source metadata on disk; the variant has one
        # consistent instruction instead of a conflicting duplicate description.
        item['styling'] = {**item.get('styling', {}), 'wearing_method': wearing,
                           'description': '', 'styling_details': [], 'overlap_relation': ''}
        item['attributes'] = {**item.get('attributes', {}), 'details': []}
    return plan, changes


def compact_prompt(context):
    items = [{'reference': x['reference_index'], 'item_id': x['item_id'],
              'garment': x['category_label'], 'wearing': x['wearing_instruction']}
             for x in context['items']]
    return (
        'Create a realistic adult everyday fashion catalogue try-on photograph. '
        'Image A is the adult target model; preserve her identity, body proportions, natural standing pose, '
        'hands, face, background, lighting, camera distance and exact canvas. '
        'Image B supplies garment designs and numbered item references only; do not copy its seated pose or scene. '
        'Apply every listed outfit item together in this single complete-outfit pass, with physically natural layering. '
        'This is an explicitly covered outerwear variation: the coverage and standing-pose instructions below '
        'take precedence where the reference garment is sheer or its wearing method differs. '
        'Opaque garments must fully cover the torso and pelvis; retain a normal closed skirt or full-length trousers. '
        'No undressing, exposed intimate anatomy or lingerie presentation. '
        'Do not lift hems or move limbs to display hidden items; allow natural occlusion. '
        'Required outfit and adjusted wearing instructions: ' + json.dumps(items, ensure_ascii=False) + '\n'
        'Keep the original reference colours, textures and recognisable details except the explicitly documented '
        'coverage adjustments. Bags and jewellery must attach naturally. Return one finished photograph only, '
        'without labels, collage, text, watermark or additional people.'
    )


@contextmanager
def generation_context(row):
    plan = read(ROOT / row['adjustedPlanPath'])
    original_runner = tryon._run_staged_outfit_edit

    def run_complete(**kwargs):
        outcome = original_runner(**kwargs)
        outcome['stage'].setdefault('evidence', {})['strategy'] = 'single_step_complete_outfit_covered_variant'
        return outcome

    with patch.object(batch, 'delivered_tryon_plan', return_value=(plan, {})), \
         patch.object(batch, 'CodexEffectProvider', AdjustedProvider), \
         patch.object(tryon, '_outfit_generation_groups', side_effect=lambda p: [('complete_outfit', p)]), \
         patch.object(tryon, '_build_outfit_tryon_prompt', side_effect=compact_prompt), \
         patch.object(tryon, '_run_staged_outfit_edit', side_effect=run_complete):
        yield


def initialize():
    VARIANT.mkdir(exist_ok=True)
    frozen = VARIANT / 'baseline-index.json'
    if not frozen.exists():
        shutil.copyfile(MAIN_INDEX, frozen)
    baseline = read(frozen)
    targets = [x for x in baseline['examples'] if x['status'] == 'blocked_moderation']
    expected = {(m, 'flou--outfits-01') for m in batch.MODELS} | {('female_medium_1', 'loop-curvy--outfits-01')}
    if {(x['modelId'], x['key']) for x in targets} != expected:
        raise ValueError('The four specifically requested blocked combinations changed')
    if batch.digest(ROOT / 'app/data/styling-delivery.v1.json') != batch.digest(BASE / 'styling-delivery.snapshot.json'):
        raise ValueError('Original delivery input changed')
    write_json_atomic(MANIFEST, {'variantId': VARIANT_ID, 'expected': 4,
        'originalRequestEquivalent': False, 'generationStrategy': 'single_step_complete_outfit_covered_variant',
        'targets': [{'id': x['id'], 'modelId': x['modelId'], 'key': x['key']} for x in targets]})
    for previous in targets:
        case = VARIANT / previous['modelId'] / previous['key']
        if (case / 'job.json').exists():
            continue
        original_plan, _ = batch.delivered_tryon_plan(previous['outfitId'], 'standard', '')
        plan, changes = adjusted_plan(original_plan, previous['noteBinding']['templateId'])
        write_json_atomic(case / 'original-plan.json', original_plan)
        write_json_atomic(case / 'adjusted-plan.json', plan)
        keys = ('id', 'modelId', 'key', 'outfitId', 'noteBinding', 'sourceAssetId', 'itemCount', 'itemIds', 'model')
        row = {k: deepcopy(previous[k]) for k in keys}
        row.update(status='queued', createdAt=batch.now(), updatedAt=batch.now(),
                   provider=AdjustedProvider.mode, strategy='single_step_complete_outfit_covered_variant',
                   artifactDir=str(case.relative_to(ROOT)), variantId=VARIANT_ID,
                   originalRequestEquivalent=False, adjustments=changes,
                   originalRequestPath=previous['requestPath'],
                   adjustedPlanPath=str((case / 'adjusted-plan.json').relative_to(ROOT)))
        write_json_atomic(case / 'job.json', row)


def selected(model=None, key=None):
    return [(p, read(p)) for p in sorted(VARIANT.glob('*/*/job.json'))
            if (not model or p.parent.parent.name == model) and (not key or p.parent.name == key)]


def publish(upload=False):
    with patch.object(batch, 'BATCH', VARIANT), patch.object(batch, 'INDEX', INDEX):
        batch.publish(upload=upload, report=False)
    payload = read(INDEX)
    c = payload['counts']
    c['expected'] = 4
    c['errors'] = sum(x['status'] == 'error' for x in payload['examples'])
    c['processed'] += c['errors']
    done = c['processed'] == 4
    payload.update(batchId=VARIANT_ID, originalRequestEquivalent=False,
                   status='completed_with_issues' if done and c['uploaded'] < 4 else 'complete' if done else 'in_progress',
                   notes=['Covered everyday outfit variants; not equivalent to the blocked original requests.',
                          'Original geometric gates retained; semantic review remains pending.'])
    write_json_atomic(INDEX, payload)
    for row in payload['examples']:
        result = row.get('result') or row.get('failedResult')
        if row['status'] not in retry.TERMINAL or result and not result.get('verified'):
            continue
        path = BASE / row['modelId'] / row['key'] / 'job.json'
        original = read(path)
        entry = {k: row[k] for k in ('variantId', 'status', 'originalRequestEquivalent', 'adjustments',
                                     'result', 'failedResult', 'visualReview', 'toolError') if k in row}
        entry['recordPath'] = str((VARIANT / row['modelId'] / row['key'] / 'job.json').relative_to(ROOT))
        original['adjustedVariants'] = [x for x in original.get('adjustedVariants', []) if x['variantId'] != VARIANT_ID] + [entry]
        write_json_atomic(path, original)
    batch.publish(report=False)
    summary = {'variantId': VARIANT_ID, 'status': payload['status'], 'counts': c,
               'originalRequestEquivalent': False, 'index': str(INDEX.relative_to(ROOT))}
    write_json_atomic(VARIANT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


def verify():
    errors = []
    rows = selected()
    completed = 0
    for path, row in rows:
        try:
            assert row['status'] in retry.TERMINAL, 'Not terminal'
            assert row['originalRequestEquivalent'] is False
            assert batch.digest(ROOT / row['model']['localPath']) == row['model']['sha256']
            requests = list((ROOT / row['workDir']).glob('stage_*/codex_request.json'))
            assert len(requests) == 1 and requests[0].parent.name == STAGE
            request = read(requests[0])
            claim = read(path.parent / 'generation-attempts' / (STAGE + '.json'))
            assert claim['attempt'] == 1 and claim['requestId'] == request['requestId']
            provenance = hashlib.sha256(request['prompt'].encode())
            for ref in request['referenced_image_paths']:
                provenance.update(Path(ref).read_bytes())
            assert provenance.hexdigest() == request['requestId']
            result = row.get('result') or row.get('failedResult')
            if result:
                source = ROOT / result['localPath']
                receipt = read(requests[0].with_name('codex_result.receipt.json'))
                assert claim['status'] == 'received' and receipt['requestId'] == request['requestId']
                assert batch.digest(source) == receipt['sha256'] == result['sha256']
                assert batch.digest(requests[0].with_name('codex_result.png')) == result['sha256']
                upload = read(batch.upload_receipt_path(source))
                asset = MaterialRegistry().get(upload['assetId'])
                assert upload['verified'] and upload['sha256'] == asset['sha256'] == result['sha256']
                if row.get('result'):
                    assert row['imageEdit']['status'] == 'pass' and row['qualityReview']['status'] != 'fail'
                else:
                    assert row['status'] == 'failed_quality' and result['qualityPassed'] is False
            else:
                assert claim['status'] == 'tool_error' and row['toolError'].get('requestId')
            completed += 1
        except (AssertionError, KeyError, OSError, ValueError) as exc:
            errors.append({'id': row['id'], 'error': str(exc)})
    current = {x['id']: x for x in read(MAIN_INDEX)['examples']}
    baseline = read(VARIANT / 'baseline-index.json')
    for old in baseline['examples']:
        now = {k: v for k, v in current[old['id']].items() if k != 'adjustedVariants'}
        expected = {k: v for k, v in old.items() if k != 'adjustedVariants'}
        if now != expected:
            errors.append({'id': old['id'], 'error': 'Original outcome changed'})
        result = old.get('result') or old.get('failedResult')
        if result and batch.digest(ROOT / result['localPath']) != result['sha256']:
            errors.append({'id': old['id'], 'error': 'Original image changed'})
    report = {'variantId': VARIANT_ID, 'completed': completed, 'expected': 4,
              'originalOutcomesUnchanged': not any('Original' in x['error'] for x in errors),
              'errors': errors, 'complete': completed == 4 and not errors}
    write_json_atomic(VARIANT / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'prepare', 'claim', 'ingest', 'finalize-failure', 'record-error', 'publish', 'verify'))
    parser.add_argument('--model', choices=batch.MODELS)
    parser.add_argument('--key')
    parser.add_argument('--stage')
    parser.add_argument('--result', type=Path)
    parser.add_argument('--error-file', type=Path)
    parser.add_argument('--upload', action='store_true')
    args = parser.parse_args()
    if args.command == 'init':
        return initialize()
    if args.command == 'publish':
        return publish(args.upload)
    if args.command == 'verify':
        return verify()
    rows = selected(args.model, args.key)
    if args.command == 'prepare':
        for path, row in rows:
            if row['status'] not in {'queued', 'pending'}:
                continue
            with generation_context(row):
                row = batch.advance(path, row)
            print(json.dumps({'id': row['id'], 'status': row['status'], 'requestPath': row.get('requestPath')}))
        return
    if not args.model or not args.key or len(rows) != 1:
        raise ValueError('Specify one --model and --key')
    path, row = rows[0]
    if args.command == 'claim':
        print(retry.claim(path, row))
        return
    if args.command == 'ingest':
        if args.stage != STAGE or not args.result:
            raise ValueError('Complete-outfit stage and result required')
        retry.active_claim(path, row, args.stage)
        with generation_context(row):
            row = batch.ingest(path, row, args.stage, args.result)
        retry.finish_claim(path, args.stage, 'received')
    elif args.command == 'finalize-failure':
        row = batch.finalize_failure(path, row)
    elif args.command == 'record-error':
        row = retry.record_error(path, row, read(args.error_file))
    print(json.dumps({'id': row['id'], 'status': row['status'], 'result': row.get('result'), 'failedResult': row.get('failedResult')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

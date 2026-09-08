"""Replay the actual outfit pipeline with image_gen results supplied by Codex.

This operator test uses isolated user storage and never changes the live provider.
Run to export the next edit request; use image_gen on its three reference images,
then run again with --stage and --result. Original geometric quality gates remain.
Semantic model calls are replaced by an explicit pending manual review, never pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import tryon
from app.material_assets import write_json_atomic
from app.storage import user_storage, storage_context
from app.styling_catalog import delivery_looks, outfit_id, delivered_tryon_plan


class CodexEffectProvider(tryon.TryOnProvider):
    mode = 'codex_builtin_imagegen_effect_test'

    def edit(self, person_image, garment_image, mask_image, prompt, output_dir):
        paths = [person_image, garment_image, mask_image]
        with Image.open(person_image) as person:
            width, height = person.size
        full_prompt = (f'Use case: identity-preserve. Edit Image A. Output exactly {width}x{height} pixels. '
                       'Image A is the target person, Image B is the labeled reference board, '
                       'Image C is the edit-region guide. Return one final photograph only.\n'
                       + tryon._build_provider_prompt_with_mask_contract(prompt))
        digest = hashlib.sha256(full_prompt.encode())
        for path in paths:
            digest.update(Path(path).read_bytes())
        request_id = digest.hexdigest()
        target = output_dir / 'codex_result.png'
        receipt_path = output_dir / 'codex_result.receipt.json'
        request = {'provider': self.mode, 'stage': output_dir.name, 'requestId': request_id,
                   'prompt': full_prompt, 'referenced_image_paths': [str(p) for p in paths],
                   'target_path': str(target), 'expectedSize': [width, height]}
        write_json_atomic(output_dir / 'codex_request.json', request)
        (output_dir / 'codex_prompt.txt').write_text(full_prompt)
        if target.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt['requestId'] != request_id or receipt['sha256'] != hashlib.sha256(target.read_bytes()).hexdigest():
                raise ValueError('Result does not belong to this edit request')
            with Image.open(target) as result:
                if result.size != (width, height):
                    return {'stage': tryon._stage('fail', 0, {'provider': self.mode, 'actualSize': list(result.size)},
                              [tryon._issue('quality.framing_changed', '结果尺寸发生变化', '请按原图尺寸重新生成。')]),
                            'image_path': None}
            return {'stage': tryon._stage('pass', 0.8, {'provider': self.mode, 'result_path': str(target),
                                                      'requestId': request_id}, []), 'image_path': target}
        return {'stage': tryon._stage('pending', 0, {'provider': self.mode,
                        'request_path': str(output_dir / 'codex_request.json')}, []), 'image_path': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', default='bolt')
    parser.add_argument('--note', default='outfits-01')
    parser.add_argument('--person', type=Path, default=ROOT / 'tests/fixtures/tryon_models/female_medium_1.png')
    parser.add_argument('--user', default='codex_effect_test_20260909')
    parser.add_argument('--stage')
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    with user_storage(args.user):
        root = storage_context().tryon_output_dir
        if args.result:
            if not args.stage:
                raise ValueError('--result requires --stage')
            requests = list(root.glob(f'*/{args.stage}/codex_request.json'))
            if len(requests) != 1:
                raise ValueError('Expected exactly one pending stage request')
            request = json.loads(requests[0].read_text())
            with Image.open(args.result) as image:
                image.verify()
            target = Path(request['target_path'])
            shutil.copyfile(args.result, target)
            write_json_atomic(target.with_name('codex_result.receipt.json'), {
                'requestId': request['requestId'], 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'tool': 'image_gen', 'sourcePath': str(args.result)})
        look = next(x for x in delivery_looks() if x['note_binding']['templateId'] == args.template
                    and x['note_binding']['noteId'] == args.note)
        plan, outfit = delivered_tryon_plan(outfit_id(look), 'standard', '')
        person = tryon._read_upload_image(args.person.read_bytes(), args.person.name, 'person')
        semantic_pending = tryon._stage('warn', 0, {'provider': 'codex_visual_review_pending', 'verified': False},
                              [tryon._issue('semantic.manual_review_required', '效果测试需要目检单品', '请核对原图与试穿结果。')])
        with patch.object(tryon, '_review_outfit_semantics', return_value=semantic_pending):
            result = tryon.run_try_on_from_outfit_plan(person, plan, provider=CodexEffectProvider(),
                                                      force_regenerate=True, wear_all_items=True)
        work = root / result['tryon_id']
        write_json_atomic(work / 'effect_test.json', {'test': 'codex_builtin_imagegen',
            'template': args.template, 'note': args.note, 'title': outfit['title'],
            'person': str(args.person), 'itemCount': len(plan['items']), 'result': result})
        print(json.dumps({'status': result['status'], 'workDir': str(work),
                          'items': len(plan['items']), 'imageEdit': result['pipeline']['image_edit'],
                          'qualityReview': result['pipeline']['quality_review']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

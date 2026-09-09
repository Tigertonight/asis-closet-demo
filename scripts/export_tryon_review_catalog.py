"""Build the Cowork review seed using existing remote images; never upload bytes.

Run with the repository Python. Signing credentials stay on this machine.
The generated, ignored seed contains temporary access URLs and must not be committed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import MaterialRegistry, material_source_url
from app.material_asset_signing import sign_qiniu_url

MODEL_IDS = ['female_slim_1', 'female_medium_1', 'female_plus_1']


def build_catalog(ttl_seconds=7 * 86400):
    batch = json.loads((ROOT / 'app/data/tryon-examples.v1.json').read_text())
    templates = json.loads((ROOT / 'app/static/selfit/data/personality-report-templates.v1.json').read_text())['types']
    delivery = json.loads((ROOT / 'app/data/styling-delivery.v1.json').read_text())['looks']
    registry = MaterialRegistry()
    assets, outfits, models = {}, {}, {}

    def asset(asset_id):
        if asset_id not in assets:
            record = registry.get(asset_id)
            url, expires = sign_qiniu_url(material_source_url(record), ttl_seconds=ttl_seconds)
            assets[asset_id] = dict(url=url, expiresAt=expires, sha256=record['sha256'])
        return asset_id

    for model in batch['sourceSnapshot']['models']:
        mid = Path(model['file']).stem
        if mid not in MODEL_IDS:
            continue
        aid = 'model_' + model['sha256']
        assets[aid] = dict(url='https://selfit.com.cn/tryon-models/' + model['file'],
                           expiresAt=None, sha256=model['sha256'])
        models[mid] = dict(id=mid, name=model['body_type_label'], image=aid)

    looks = {(l['note_binding']['templateId'], l['note_binding']['noteId']): l for l in delivery}
    for example in batch['examples']:
        binding = example['noteBinding']
        oid = example['outfitId']
        if oid not in outfits:
            look = looks[(binding['templateId'], binding['noteId'])]
            note_url = re.search(r'https://www\.xiaohongshu\.com/[^\s]+', binding.get('sourceUrl', ''))
            outfits[oid] = dict(id=oid, name=binding['name'], persona=binding['persona'],
                personaName=templates[binding['persona']]['metadata']['name'],
                bodyProfile=binding['bodyProfile'], position=binding['position'],
                templateId=binding['templateId'], noteId=binding['noteId'],
                byline=binding.get('byline', ''), noteUrl=note_url.group(0) if note_url else None,
                source=asset(example['sourceAssetId']),
                items=[i['garment_name'] for i in look['items']], results=[])
        result = example.get('result') or example.get('failedResult')
        variant = next((v for v in example.get('adjustedVariants', []) if v.get('result')), None)
        if not result and variant:
            result = variant['result']
        adjusted = bool(variant and result is variant['result'])
        selected = variant if adjusted else example
        review = selected.get('visualReview') or {}
        warnings = review.get('observedIssues') or []
        if isinstance(warnings, str):
            warnings = [warnings]
        image_id = asset(result['assetId']) if result else None
        outfits[oid]['results'].append(dict(
            id=example['id'], modelId=example['modelId'], image=image_id,
            reviewKey=example['id'] + ':' + (result['sha256'] if result else 'missing'),
            originalStatus=example['status'], adjusted=adjusted,
            variantId=selected.get('variantId') if adjusted else None,
            originalRequestEquivalent=not adjusted,
            adjustments=selected.get('adjustments', []) if adjusted else [],
            warnings=warnings,
        ))
    order = list(templates)
    rows = sorted(outfits.values(), key=lambda o: (order.index(o['persona']), o['bodyProfile'] != 'standard', o['position']))
    for row in rows:
        row['results'].sort(key=lambda r: MODEL_IDS.index(r['modelId']))
        assert [r['modelId'] for r in row['results']] == MODEL_IDS
    available = sum(bool(r['image']) for row in rows for r in row['results'])
    assert len(rows) == 80 and available == 239 and len(models) == 3
    return dict(schemaVersion=1, batchId=batch['batchId'], createdAt=datetime.now(timezone.utc).isoformat(),
        expiresAt=min(a['expiresAt'] for a in assets.values() if a['expiresAt']),
        models=[models[mid] for mid in MODEL_IDS], outfits=rows, assets=assets,
        counts=dict(outfits=len(rows), expected=240, available=available, missing=240-available,
                    adjusted=sum(r['adjusted'] for row in rows for r in row['results'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'cowork/tryon-review/seeds/catalog.json')
    parser.add_argument('--days', type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.days <= 30:
        parser.error('--days must be between 1 and 30')
    catalog = build_catalog(args.days * 86400)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))
    args.output.chmod(0o600)
    print(json.dumps({'counts': catalog['counts'], 'expiresAt': catalog['expiresAt'], 'output': str(args.output)}))

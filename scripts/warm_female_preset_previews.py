"""Cache verified female preset previews so their temporary URLs can expire safely."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, material_image_path


def warm(index, registry, expected=None, workers=3):
    if expected is None:
        expected = index.get('femaleOneShotBatch', {}).get('expected')
        if not isinstance(expected, int) or expected <= 0:
            raise ValueError('Missing female preset target')
    rows = [row for row in index['examples'] if row.get('model', {}).get('gender') == 'female'
            and row.get('strategy') == 'complete_outfit_single_call']
    if len(rows) != expected or len({row['id'] for row in rows}) != expected:
        raise ValueError('Unexpected female preset count')
    assets = []
    for row in rows:
        display = row.get('displayResult', {})
        if (row.get('status') != 'uploaded' or not display.get('verified')
                or display.get('sourceSha256') != row['result']['sha256']):
            raise ValueError('Unverified preset preview: ' + row['id'])
        record = registry.get(display['assetId'])
        if record['sha256'] != display['sha256'] or record['contentType'] != 'image/webp':
            raise ValueError('Preset preview registry mismatch: ' + row['id'])
        assets.append((display['assetId'], display['sha256']))

    def fetch(asset):
        asset_id, digest = asset
        path = material_image_path(asset_id, registry)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Preset preview cache mismatch: ' + asset_id)
        return path.stat().st_size

    with ThreadPoolExecutor(max_workers=workers) as pool:
        sizes = list(pool.map(fetch, assets))
    return {'cachedPreviews': len(sizes), 'bytes': sum(sizes), 'sha256Verified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'app/data/tryon-examples.v1.json')
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--expected', type=int, help='Defaults to the active female batch target in the index')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    result = warm(json.loads(args.index.read_text()), MaterialRegistry(args.registry), args.expected, args.workers)
    print(json.dumps(result))

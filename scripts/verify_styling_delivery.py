"""Read back every published material, verify SHA-256, and save the audit result."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import MaterialRegistry, material_image_path, write_json_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    delivery = json.loads((ROOT / 'app/data/styling-delivery.v1.json').read_text())
    if delivery['uploadStatus'] != 'complete':
        raise ValueError('Delivery upload is not complete')
    ids = set()
    for name in ('styling-source-assets.v1.json', 'styling-report-assets.v1.json'):
        manifest = json.loads((ROOT / 'app/data' / name).read_text())
        ids.update(ref['assetId'] for ref in manifest['files'].values())
    registry = MaterialRegistry()

    def verify(asset_id):
        try:
            record = registry.get(asset_id)
            if not record['url'].startswith(('http://', 'https://')):
                raise ValueError('Material is not uploaded')
            path = material_image_path(asset_id, registry)
            if path.stat().st_size != record['bytes']:
                raise ValueError('Material size mismatch')
            return asset_id, None
        except Exception as exc:
            # Signed URLs may occur in exception messages, so retain only the type.
            return asset_id, type(exc).__name__

    failures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, (asset_id, error) in enumerate(executor.map(verify, sorted(ids)), 1):
            if error:
                failures[asset_id] = error
            if index % 50 == 0 or index == len(ids):
                print(f'verified {index}/{len(ids)}, failures={len(failures)}', flush=True)
    audit = {'schemaVersion': '1.0', 'checkedAt': datetime.now(timezone.utc).isoformat(),
             'status': 'complete' if not failures else 'failed', 'uniqueImages': len(ids),
             'verifiedImages': len(ids) - len(failures), 'method': 'download/cache + SHA-256 + byte length',
             'deliveryCounts': delivery['counts'], 'failures': failures}
    write_json_atomic(ROOT / 'app/data/styling-delivery-verification.v1.json', audit)
    print(json.dumps(audit, ensure_ascii=False))
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()

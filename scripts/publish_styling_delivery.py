"""Upload delivered images plus the selected report images, then finalize bindings.

Credentials are read from --env-file using provider-specific variables. Only completed
uploads enter the material registry; the delivery is finalized only when every
referenced image has an OSS/CDN URL. Source delivery files stay untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, write_json_atomic
from app.selfit_assets import _oss_bucket_from_env
from scripts.register_styling_delivery import build_delivery, DESTINATION, MASTER
from scripts.upload_content_pool import OssUploadClient, upload_directory


def selected_report_images(master: dict) -> list[Path]:
    paths = set()
    for t in master['templates']:
        urls = [t.get('hero', '')]
        urls.extend(i.get('image', '') for group in ('makeup', 'hair', 'outfits') for i in t.get(group, []))
        for url in urls:
            parsed = urlsplit(url)
            if not parsed.path.startswith('/static/') or parsed.netloc or parsed.scheme:
                raise ValueError('Report images must be materialized locally before upload')
            path = (ROOT / 'app' / unquote(parsed.path.lstrip('/'))).resolve()
            if not path.is_relative_to(ROOT / 'app/static') or not path.is_file():
                raise ValueError(f'Missing local report image: {parsed.path}')
            paths.add(path)
    return sorted(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--backend', choices=('oss', 'qiniu'), default='oss')
    parser.add_argument('--public-base', required=True)
    parser.add_argument('--prefix', default='selfit/materials/siri-styling-v1')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    master = json.loads(MASTER.read_text())
    selected = selected_report_images(master)
    registry = MaterialRegistry()
    # Validate the entire delivery before any outbound upload.
    build_delivery(args.source, master, registry)
    if args.backend == 'qiniu':
        from scripts.qiniu_material_upload import qiniu_client_from_env
        client = qiniu_client_from_env(args.bucket)
    else:
        client = OssUploadClient(_oss_bucket_from_env())
    common = dict(client=client, bucket=args.bucket, public_base=args.public_base,
                  prefix=args.prefix, registry=registry, workers=args.workers)
    upload_directory(args.source, **common, manifest_path=ROOT / 'app/data/styling-source-assets.v1.json')
    upload_directory(ROOT / 'app/static', **common, image_paths=selected,
                     manifest_path=ROOT / 'app/data/styling-report-assets.v1.json')
    delivery = build_delivery(args.source, master, registry, require_uploaded=True)
    write_json_atomic(DESTINATION, delivery)
    print(json.dumps({'status': 'complete', **delivery['counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

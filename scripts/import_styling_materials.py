"""Make delivered cutout images available locally without changing existing CDN bindings.

Usage: python scripts/import_styling_materials.py --source /path/to/拆款交付-siri-styling
Only images referenced by the committed delivery are copied. Source files stay untouched.
"""
from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, asset_id_for_bytes
from app.styling_catalog import delivery_looks


def import_materials(source: Path) -> dict:
    source = source.resolve()
    registry = MaterialRegistry()
    pending = {}
    for look in delivery_looks():
        for item in look['items']:
            asset_id = item['image_asset']['assetId']
            try:
                registry.get(asset_id)
                continue
            except KeyError:
                pass
            path = (source / Path(look['source_path']).parent / item['asset_filename']).resolve()
            if not path.is_relative_to(source):
                raise ValueError('Image path escapes the delivery')
            raw = path.read_bytes()
            if asset_id_for_bytes(raw) != asset_id:
                raise ValueError(f'Image content changed: {path.name}')
            pending[asset_id] = (path.suffix.lower(), raw)
    # Validate all bytes before writing or registering any image.
    target = ROOT / 'app/static/selfit/assets/styling-delivery'
    target.mkdir(parents=True, exist_ok=True)
    for asset_id, (extension, raw) in pending.items():
        destination = target / (asset_id + extension)
        destination.write_bytes(raw)
        registry.register(raw, '/' + destination.relative_to(ROOT / 'app').as_posix(),
                          mimetypes.guess_type(destination.name)[0] or 'image/png', replace_url=False)
    return {'registered': len(pending), 'status': 'ready'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    print(import_materials(parser.parse_args().source))


if __name__ == '__main__':
    main()

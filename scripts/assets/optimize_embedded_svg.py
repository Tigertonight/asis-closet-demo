"""Losslessly reduce embedded raster payloads without changing SVG geometry.

Usage: python scripts/assets/optimize_embedded_svg.py path.svg [...]
Only replaces an image when its decoded RGBA bytes are identical and it is smaller.
Figma export originals remain in docs/audits as provenance.
"""
import base64
import io
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image

ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def optimize(path):
    path = Path(path)
    original = path.read_bytes()
    root = ET.fromstring(original)
    changes = []
    for node in root.iter('{http://www.w3.org/2000/svg}image'):
        for key, value in list(node.attrib.items()):
            if not key.endswith('href') or not value.startswith('data:image/'):
                continue
            header, encoded = value.split(',', 1)
            if ';base64' not in header:
                continue
            payload = base64.b64decode(encoded)
            source = Image.open(io.BytesIO(payload))
            if getattr(source, 'n_frames', 1) != 1:
                continue
            rgba = source.convert('RGBA')
            buffer = io.BytesIO()
            rgba.save(buffer, format='WEBP', lossless=True, exact=True, method=6)
            candidate = buffer.getvalue()
            if len(candidate) >= len(payload):
                continue
            decoded = Image.open(io.BytesIO(candidate)).convert('RGBA')
            if rgba.size != decoded.size or rgba.tobytes() != decoded.tobytes():
                raise ValueError(f'Pixel mismatch: {path}:{node.get("id")}')
            node.set(key, 'data:image/webp;base64,' + base64.b64encode(candidate).decode())
            changes.append({'id': node.get('id'), 'before': len(payload), 'after': len(candidate), 'rgba_equal': True})
    if changes:
        rendered = ET.tostring(root, encoding='utf-8')
        if len(rendered) < len(original):
            path.write_bytes(rendered)
    return {'file': str(path), 'before': len(original), 'after': path.stat().st_size, 'images': changes}


if __name__ == '__main__':
    print(json.dumps([optimize(path) for path in sys.argv[1:]], ensure_ascii=False, indent=2))

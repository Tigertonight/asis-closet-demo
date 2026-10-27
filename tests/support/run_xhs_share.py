"""Local UI QA using a synthetic stamp and stub share preparation; never calls XHS or publishes.
Run: .venv/bin/python tests/support/run_xhs_share.py
Open /test/xhs-receipt. Launch URLs are placeholders: inspect the UI without opening them.
"""
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
from app import selfit_mirror_photos as photos, selfit_xhs_share as xhs

os.environ['SELFIT_PUBLIC_BASE_URL'] = 'http://127.0.0.1:8789'
os.environ['SELFIT_XHS_APP_KEY'] = 'qa-only-key'
os.environ['SELFIT_XHS_APP_SECRET'] = 'qa-only-secret'
photos.PHOTO_DIR = Path(tempfile.mkdtemp(prefix='selfit-xhs-ui-'))
def fake_prepare(image_url, page_url, agent):
    from urllib.parse import urlencode
    scheme = 'xhsdiscover://js_share_sdk?' + urlencode({'share_code': 'qa-only-code', 'app_key': 'qa-only-key', 'session_id': 'qa-session'})
    return {
        'verifyConfig': {'appKey': 'qa-only-key'},
        'shareInfo': {'type': 'normal', 'images': [image_url]},
        'expiresAt': int(time.time() * 1000) + 180000,
        'launch': {'scheme': scheme, 'universal': 'https://oia.xiaohongshu.com/oia?' + urlencode({'deeplink': scheme}), 'platform': 'Android', 'inWeChat': False},
    }
xhs.prepare_share = fake_prepare
image = Image.new('RGB', (900, 1200), '#c8d2e5')
draw = ImageDraw.Draw(image)
draw.rectangle((70, 80, 830, 1100), outline='#174fe4', width=5)
draw.text((120, 430), 'WOKEN DAY', font_size=80, fill='#174fe4')
draw.text((130, 570), 'SHARE PREVIEW', font_size=65, fill='#174fe4')
draw.text((220, 700), 'TEST PHOTO', font_size=55, fill='#174fe4')
original, final = io.BytesIO(), io.BytesIO()
image.save(original, 'JPEG'); image.save(final, 'PNG')
secret = secrets.token_hex(32)
record = photos._save(original.getvalue(), final.getvalue(), json.dumps({'template': 'woken-stamp'}), secret)
app = FastAPI()


@app.get('/test/xhs-receipt')
def receipt_fixture():
    script = f"""<script>
    history.replaceState(null, '', location.pathname + location.search + '#{record['id']}.{secret}');
    // Deterministic recovery UI without calling XHS or launching a native app.
    if (new URLSearchParams(location.search).get('mode') === 'share-failure') {{
      const realFetch = window.fetch.bind(window);
      window.fetch = (url, options) => url.endsWith('/xhs-share')
        ? Promise.resolve(new Response(JSON.stringify({{detail: '分享暂时不可用，可以重试或先保存照片。'}}), {{status: 503, headers: {{'Content-Type': 'application/json'}}}}))
        : realFetch(url, options);
    }}
    </script>"""
    return HTMLResponse((ROOT / 'app/static/selfit/mirror-photo.html').read_text().replace('</head>', script + '</head>'))


app.include_router(photos.router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8789)

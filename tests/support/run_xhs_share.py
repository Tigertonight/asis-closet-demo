"""Local UI QA using a synthetic stamp and stub SDK; never calls XHS or publishes.
Run: .venv/bin/python tests/support/run_xhs_share.py
Open /test/xhs-receipt?mode=ok|fail|slow. Production files retain the real SDK.
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
xhs.verify_config = lambda: {
    'verifyConfig': {'appKey': 'qa-only-key', 'nonce': 'qa-nonce', 'timestamp': str(int(time.time() * 1000)), 'signature': 'qa-signature'},
    'expiresAt': int(time.time() * 1000) + 180000,
}
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
    Object.defineProperty(navigator, 'userAgent', {{value: 'iPhone MicroMessenger/8.0', configurable: true}});
    history.replaceState(null, '', location.pathname + location.search + '#{record['id']}.{secret}');
    sessionStorage.setItem('selfit.qa.xhsMode', new URLSearchParams(location.search).get('mode') || 'ok');
    </script>"""
    return HTMLResponse((ROOT / 'app/static/selfit/mirror-photo.html').read_text().replace('</head>', script + '</head>'))


@app.get('/selfit/photo/share')
def share_fixture():
    script = """<script>
    Object.defineProperty(navigator, 'userAgent', {value: 'iPhone MicroMessenger/8.0', configurable: true});
    const append = document.head.append.bind(document.head);
    document.head.append = node => {
      if (node.src === 'https://fe-static.xhscdn.com/biz-static/goten/xhs-1.0.1.js') {
        window.xhs = { share: async input => {
          document.documentElement.dataset.sdkCalls = String(Number(document.documentElement.dataset.sdkCalls || 0) + 1);
          document.documentElement.dataset.sdkType = input.shareInfo.type;
          document.documentElement.dataset.sdkImages = String(input.shareInfo.images.length);
          const mode = sessionStorage.getItem('selfit.qa.xhsMode');
          if (mode === 'fail') input.fail({errCode: 20003});
          if (mode === 'slow') await new Promise(() => {});
        }};
        queueMicrotask(() => node.onload()); return;
      }
      append(node);
    };
    </script>"""
    return HTMLResponse((ROOT / 'app/static/selfit/mirror-xhs-share.html').read_text().replace('</head>', script + '</head>'))


app.include_router(photos.router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8789)

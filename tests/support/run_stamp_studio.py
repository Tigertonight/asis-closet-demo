"""Isolated local UI QA: no external storage, AI calls, or user data writes.
Run: .venv/bin/python tests/support/run_stamp_studio.py
Normal /selfit/stamp uses real camera; /test/stamp uses a synthetic video stream.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['SELFIT_ASSET_STORE'] = 'local'
os.environ['SELFIT_PUBLIC_BASE_URL'] = 'http://127.0.0.1:8788'
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app import selfit_mirror_photos

# App imports may load the developer .env. Override afterward as well: this
# harness must never upload QA captures into configured external storage.
os.environ['SELFIT_ASSET_STORE'] = 'local'
os.environ['SELFIT_PUBLIC_BASE_URL'] = 'http://127.0.0.1:8788'

selfit_mirror_photos.PHOTO_DIR = Path(tempfile.mkdtemp(prefix='selfit-studio-qa-'))
app = FastAPI()
app.include_router(selfit_mirror_photos.router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

@app.get('/test/stamp')
def camera_fixture(mode: str = 'success'):
    # Test-only injection: no device permission, no actual camera capture.
    script = """<script>
    const qa = document.documentElement.dataset;
    qa.cameraRequests = '0'; qa.cameraStops = '0'; qa.saveAttempts = '0';
    const realFetch = window.fetch.bind(window);
    window.fetch = async (url, options) => {
      if (url === '/api/v1/selfit/mirror/photos' && options?.method === 'POST') {
        qa.saveAttempts = String(Number(qa.saveAttempts) + 1);
        if (new URLSearchParams(location.search).get('mode') === 'save-failure' && qa.saveAttempts === '1') throw new TypeError('Test offline');
      }
      return realFetch(url, options);
    };
    navigator.mediaDevices.getUserMedia = async () => {
      qa.cameraRequests = String(Number(qa.cameraRequests) + 1);
      const mode = new URLSearchParams(location.search).get('mode');
      if (mode === 'denied') throw new DOMException('Test permission denied', 'NotAllowedError');
      const c = document.createElement('canvas'); c.width = 1080; c.height = 1920;
      const x = c.getContext('2d'); x.fillStyle = '#ded4c9'; x.fillRect(0,0,1080,1920);
      x.fillStyle = '#d64d63'; x.fillRect(0,0,270,1920);
      x.fillStyle = '#364c74'; x.fillRect(810,0,270,1920);
      x.fillStyle = '#4c4740'; x.font = '80px sans-serif'; x.fillText('TOP',420,220); x.fillText('BOTTOM',340,1740);
      if (new URLSearchParams(location.search).get('photo') === 'portrait') {
        const img = new Image(); img.src = '/static/selfit/assets/samples/female-body-sample-v2.jpg'; await img.decode();
        x.drawImage(img, 0, 0, c.width, c.height);
      }
      const stream = c.captureStream(10);
      const timer = setInterval(() => { x.fillStyle = '#ded4c9'; x.fillRect(0,0,1,1); }, 100);
      stream.getTracks().forEach(t => { const stop = t.stop.bind(t); t.stop = () => { qa.cameraStops = String(Number(qa.cameraStops) + 1); clearInterval(timer); stop(); }; });
      if (mode === 'late') await new Promise(r => setTimeout(r, 4000));
      return stream;
    };
    </script>"""
    html = (ROOT / 'app/static/selfit/stamp/index.html').read_text()
    return HTMLResponse(html.replace('</head>', script + '</head>'))

if __name__ == '__main__':
    import uvicorn
    print(f'Isolated photo data: {selfit_mirror_photos.PHOTO_DIR}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=8788)

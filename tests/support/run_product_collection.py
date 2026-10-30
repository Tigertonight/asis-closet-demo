"""Isolated local QA. Real intake DB/API + real admin UI, fake admin auth only.
Run with .venv/bin/python tests/support/run_product_collection.py, bound to loopback.
Test records are stored in a fresh temporary directory, never production outputs.
"""
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app import product_collection as pc
from app.auth import get_admin_user

pc.STORE = Path(tempfile.mkdtemp(prefix='selfit-products-qa-'))
app = FastAPI()
app.include_router(pc.router)
app.dependency_overrides[get_admin_user] = lambda: {'user_id': 'local-qa-only'}
app.mount('/static', StaticFiles(directory=ROOT/'app/static'), name='static')
@app.get('/admin')
def admin():
    html=(ROOT/'app/static/admin/index.html').read_text()
    return HTMLResponse(html.replace('<head>','<head><script>sessionStorage.setItem("selfit.admin.token.v1","local-qa-only");</script>'))
@app.get('/admin/api/analytics/summary')
def summary():
    return dict(totals={}, appFunnel=[], mirrorFunnel=[], dwell={}, hourly=[], users=[])
@app.get('/admin/api/analytics/users')
def users():
    return {'users':[]}
if __name__=='__main__':
    import uvicorn
    print('Isolated QA DB:',pc.STORE,flush=True)
    uvicorn.run(app,host='127.0.0.1',port=8793)

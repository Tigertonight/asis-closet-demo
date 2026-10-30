"""Isolated local QA: real intake/auth/API with a temporary database.

--password-file can use the owner's local credential for browser acceptance;
without it, only the documented local test password is accepted.
"""
import argparse
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import product_collection as pc, product_collection_auth as auth
from app.ops import request_guard_middleware


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8794)
    parser.add_argument('--password-file', type=Path)
    args = parser.parse_args()
    pc.STORE = Path(tempfile.mkdtemp(prefix='selfit-products-qa-'))
    auth.AUTH_DB = pc.STORE / 'admin.sqlite3'
    password = args.password_file.read_text().strip() if args.password_file else 'collection-local-qa-only'
    auth.configure_password(password)
    app = FastAPI(); app.include_router(pc.router)
    app.middleware('http')(request_guard_middleware)
    app.mount('/static', StaticFiles(directory=ROOT/'app/static'), name='static')
    import uvicorn
    print('Isolated QA DB:', pc.STORE, flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()

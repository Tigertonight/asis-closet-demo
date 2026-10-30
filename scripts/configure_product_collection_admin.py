#!/usr/bin/env python3
"""Generate or rotate the independent collection admin password on this machine.

Run with the project venv. Only salted password hashes are stored by the app;
a private credential handoff file under ignored outputs/ is created for the owner.
"""
import argparse
import os
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import product_collection_auth as auth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rotate', action='store_true', help='replace existing password and revoke collection sessions')
    parser.add_argument('--auth-db', type=Path, help='optional isolated QA auth database')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/credentials/product-collection-admin.txt')
    args = parser.parse_args()
    if args.auth_db:
        auth.AUTH_DB = args.auth_db
    with auth.database() as db:
        exists = db.execute('SELECT 1 FROM password WHERE id=1').fetchone()
    if exists and not args.rotate:
        raise SystemExit('Password already configured; use --rotate only when intentionally replacing it.')
    password = ''.join(secrets.choice(string.ascii_letters + string.digits + '-_') for _ in range(24))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not overwrite a prior credential handoff by accident.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        auth.configure_password(password)
        with os.fdopen(fd, 'w') as out:
            out.write(password + '\n')
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    print('Independent password configured. Private handoff file:', args.output)


if __name__ == '__main__':
    main()

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def cleanup_users(root: Path, max_age_days: int, dry_run: bool = False) -> dict[str, object]:
    users_dir = root / "outputs" / "users"
    cutoff = time.time() - max_age_days * 24 * 60 * 60
    removed: list[str] = []
    kept = 0
    if not users_dir.exists():
        return {"status": "ok", "users_dir": str(users_dir), "removed": removed, "kept": kept}

    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        if user_dir.name == "local_user":
            kept += 1
            continue
        latest_mtime = max((path.stat().st_mtime for path in user_dir.rglob("*") if path.exists()), default=user_dir.stat().st_mtime)
        if latest_mtime >= cutoff:
            kept += 1
            continue
        removed.append(str(user_dir))
        if not dry_run:
            shutil.rmtree(user_dir, ignore_errors=True)

    return {"status": "ok", "users_dir": str(users_dir), "max_age_days": max_age_days, "dry_run": dry_run, "removed": removed, "kept": kept}


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove stale demo user uploads and generated outputs.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = cleanup_users(args.root, max(1, args.days), args.dry_run)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


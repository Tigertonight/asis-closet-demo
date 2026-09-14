"""Keep the ten newest complete code backups; never prune runtime backups."""
from pathlib import Path
import re
import shutil


def prune_backups(root: Path, keep: int = 10) -> list[str]:
    if keep < 1:
        raise ValueError("At least one backup must be retained")
    if not root.exists():
        return []
    backups = sorted(
        path for path in root.iterdir()
        if not path.is_symlink() and path.is_dir()
        and re.fullmatch(r"\d{8}-\d{6}", path.name)
    )
    removed = []
    for path in backups[:-keep]:
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


if __name__ == "__main__":
    removed = prune_backups(Path("/opt/selfit/deploy-backups"))
    print(f"[deploy] Removed {len(removed)} old code backups; keeping latest 10")

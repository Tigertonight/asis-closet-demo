import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "prune_deploy_backups", Path(__file__).parents[1] / "scripts/prune_deploy_backups.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_keeps_latest_ten_and_preserves_runtime_and_symlinks(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    names = [f"202609{i:02d}-120000" for i in range(1, 13)]
    for name in reversed(names):
        (root / name).mkdir()
        (root / name / "code").write_text("backup")
    runtime = root / "runtime-release-test"
    runtime.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "user-data").write_text("preserve")
    (root / "20260801-120000").symlink_to(outside, target_is_directory=True)
    assert module.prune_backups(root) == names[:2]
    assert all((root / name).exists() for name in names[2:])
    assert runtime.exists()
    assert (outside / "user-data").read_text() == "preserve"
    assert module.prune_backups(root) == []

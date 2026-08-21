from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_DIR = ROOT / "vendor" / "toolchains"
GO_ROOT = TOOLCHAIN_DIR / "go"


def _go_arch() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    go_os = {"darwin": "darwin", "linux": "linux"}.get(system)
    go_arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(machine)
    if not go_os or not go_arch:
        raise SystemExit(f"Unsupported platform for vendored Go: {system}/{machine}")
    return go_os, go_arch


def _latest_go_archive(go_os: str, go_arch: str) -> tuple[str, str]:
    with urllib.request.urlopen("https://go.dev/dl/?mode=json", timeout=30) as response:
        releases = json.loads(response.read().decode("utf-8"))
    for release in releases:
        for file_info in release.get("files", []):
            if file_info.get("os") == go_os and file_info.get("arch") == go_arch and file_info.get("kind") == "archive":
                return release["version"], file_info["filename"]
    raise SystemExit(f"No Go archive found for {go_os}/{go_arch}")


def main() -> int:
    go_os, go_arch = _go_arch()
    version, filename = _latest_go_archive(go_os, go_arch)
    TOOLCHAIN_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = TOOLCHAIN_DIR / filename
    url = f"https://go.dev/dl/{filename}"
    if not archive_path.exists():
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:
            archive_path.write_bytes(response.read())
    if GO_ROOT.exists():
        shutil.rmtree(GO_ROOT)
    with tarfile.open(archive_path) as archive:
        archive.extractall(TOOLCHAIN_DIR)
    go_bin = GO_ROOT / "bin" / "go"
    subprocess.run([str(go_bin), "version"], check=True)
    (ROOT / "go-runtime.lock.json").write_text(
        json.dumps(
            {
                "version": version,
                "filename": filename,
                "go_root": str(GO_ROOT),
                "go_bin": str(go_bin),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Vendored Go ready at {go_bin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

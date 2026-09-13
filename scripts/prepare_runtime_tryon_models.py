"""Prepare verified model runtime data without changing Git-owned originals."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, name):
    if not name or Path(name).name != name:
        raise ValueError("Model file must be a basename")
    path = (root / name).resolve()
    if path.parent != root.resolve() or not path.is_file():
        raise ValueError("Missing model original: " + name)
    return path


def prepare(shared, originals, overrides_path, output_root):
    shared, originals, output_root = map(Path, (shared, originals, output_root))
    manifest = json.loads((shared / "manifest.json").read_text())
    overrides = json.loads(Path(overrides_path).read_text())["models"]
    merged = deepcopy(manifest)
    files, matched = {}, set()
    for index, row in enumerate(manifest["items"]):
        mid = row.get("id") or Path(row["file"]).stem
        if mid in overrides:
            replacement = overrides[mid]
            metadata = replacement["metadata"]
            if (metadata.get("file") != row["file"] or metadata.get("gender") != row.get("gender")
                    or (metadata.get("id") or Path(metadata["file"]).stem) != mid
                    or metadata.get("image_asset_id")):
                raise ValueError("Replacement model identity changed: " + mid)
            source = safe_file(originals, row["file"])
            if digest(source) != replacement["sha256"]:
                raise ValueError("Replacement model hash mismatch: " + mid)
            with Image.open(source) as image:
                if image.size != (metadata["width"], metadata["height"]):
                    raise ValueError("Replacement dimensions mismatch: " + mid)
                image.verify()
            merged["items"][index] = metadata
            matched.add(mid)
        elif row.get("image_asset_id"):
            continue  # Existing object-storage models retain their registered identity.
        else:
            source = safe_file(shared, row["file"])
        files[row["file"]] = {"source": source, "sha256": digest(source)}
    if matched != set(overrides):
        raise ValueError("Replacement contains unknown models")
    receipt = {"manifest": merged, "files": {name: value["sha256"] for name, value in files.items()}}
    identity = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    target = output_root / identity

    def verify(directory):
        if json.loads((directory / "manifest.json").read_text()) != merged:
            raise ValueError("Runtime manifest changed")
        if (directory / "manifest.local.json").exists():
            raise ValueError("Unexpected local metadata override")
        for name, value in files.items():
            if digest(safe_file(directory, name)) != value["sha256"]:
                raise ValueError("Runtime original changed: " + name)

    if target.exists():
        verify(target)
    else:
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".prepare-models-", dir=output_root))
        try:
            for name, value in files.items():
                shutil.copyfile(value["source"], temporary / name)
            (temporary / "manifest.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
            (temporary / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            verify(temporary)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"directory": str(target.resolve()), "identity": identity,
            "models": len(merged["items"]), "replaced": sorted(matched), "verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", type=Path, default=ROOT / "tests/fixtures/tryon_models")
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, default=ROOT / "app/data/female-nano-models.v1.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/runtime/tryon-models")
    args = parser.parse_args()
    print(json.dumps(prepare(args.shared, args.originals, args.overrides, args.output_root), ensure_ascii=False))

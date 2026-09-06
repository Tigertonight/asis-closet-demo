"""Review evidence must track bytes, not filesystem timestamps."""
import hashlib
import json
import os

from app import recommendation_visual as visual


def test_asset_replacement_with_same_size_and_mtime_invalidates_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(visual, "ROOT", tmp_path)
    path = tmp_path / "app/static/sample.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old-image")
    stamp = path.stat()
    assert visual.asset_sha("/static/sample.png") == hashlib.sha256(b"old-image").hexdigest()
    path.write_bytes(b"new-image")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert visual.asset_sha("/static/sample.png") == hashlib.sha256(b"new-image").hexdigest()
    path.unlink()
    assert visual.asset_sha("/static/sample.png") is None


def test_review_replacement_with_preserved_mtime_is_read(tmp_path, monkeypatch):
    path = tmp_path / "visual.json"
    monkeypatch.setenv("SELFIT_RECOMMENDATION_VISUAL_PATH", str(path))
    initial = {"schema_version": 1, "outfits": {"sample": {"status": "ai_candidate"}}}
    path.write_text(json.dumps(initial))
    stamp = path.stat()
    assert visual.load_visual()["outfits"]["sample"]["status"] == "ai_candidate"
    initial["outfits"]["sample"]["status"] = "needs_review"
    path.write_text(json.dumps(initial))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert visual.load_visual()["outfits"]["sample"]["status"] == "needs_review"
    path.write_text("{broken")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert visual.load_visual()["status"] == "pending_vision"
    path.unlink()
    assert visual.load_visual()["status"] == "pending_vision"

"""The P0 performance filter never substitutes for release admission."""
import json
import os

import pytest

from app import recommendation_anchors as anchors


def setup_workset(tmp_path, monkeypatch):
    path = tmp_path / "anchors.json"
    monkeypatch.setenv("SELFIT_P0_ANCHOR_MANIFEST", str(path))
    catalog = [{"outfit_id": str(i)} for i in range(200)]
    manifest = {"anchors": catalog[:160]}
    path.write_text(json.dumps(manifest))
    return path, catalog, manifest


def test_workset_only_reduces_to_manifest_ids_without_mutation(tmp_path, monkeypatch):
    _, catalog, _ = setup_workset(tmp_path, monkeypatch)
    assert anchors.anchor_visual_workset(catalog) == catalog[:160]
    assert len(catalog) == 200
    assert all(set(row) == {"outfit_id"} for row in catalog)


@pytest.mark.parametrize("entries", [None, [], [{}] * 160,
    [{"outfit_id": "same"}] * 160, [{"outfit_id": []}] * 160])
def test_bad_workset_is_empty(tmp_path, monkeypatch, entries):
    path, catalog, _ = setup_workset(tmp_path, monkeypatch)
    path.write_text(json.dumps({"anchors": entries}))
    assert anchors.anchor_visual_workset(catalog) == []


def test_preserved_mtime_does_not_reuse_workset(tmp_path, monkeypatch):
    path, catalog, manifest = setup_workset(tmp_path, monkeypatch)
    stamp = path.stat()
    assert anchors.anchor_visual_workset(catalog) == catalog[:160]
    manifest["anchors"] = catalog[1:161]
    path.write_text(json.dumps(manifest))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert anchors.anchor_visual_workset(catalog) == catalog[1:161]
    path.unlink()
    assert anchors.anchor_visual_workset(catalog) == []


def test_workset_is_not_approval(tmp_path, monkeypatch):
    _, catalog, _ = setup_workset(tmp_path, monkeypatch)
    monkeypatch.setenv("SELFIT_P0_BLIND_REVIEW", str(tmp_path / "missing.json"))
    workset = anchors.anchor_visual_workset(catalog)
    assert len(workset) == 160
    released, report = anchors.approved_anchor_pool(workset, [], content_version="v1", visual_version="v1")
    assert released == [] and report["valid"] is False

from collections import Counter
import json
import os

from app.recommendation_diversity import outfit_features, select_diverse_outfits, style_family_map
from app.selfit_content_quality import record_fingerprint


def outfit(oid, main, parent=None, family=None):
    return {"outfit_id": oid, "parent_outfit_id": parent,
            "items": [{"item_id": main, "category": "bottom", "style_family_id": family}]}


def assert_constraints(rows):
    features = [outfit_features(o) for o in rows]
    for i, feature in enumerate(features):
        assert feature[0] not in {f[0] for f in features[max(0, i-7):i]}
        for dimension in (1, 2):
            counts = Counter(v for f in features[max(0, i-9):i+1] for v in f[dimension])
            assert max(counts.values(), default=0) <= 2


def test_cross_page_main_family_and_parent_limits():
    ranked = [outfit(f"o{i}", f"g{i//5}", f"parent{i//3}", f"family{i//10}") for i in range(150)]
    seen, rows = [], []
    for _ in range(8):
        page = select_diverse_outfits(ranked, seen, 6)
        rows.extend(page["outfits"])
        seen.extend(o["outfit_id"] for o in page["outfits"])
        ranked.reverse()  # exposure/score order can change between calls
        assert_constraints(rows)
    assert len(rows) == 48 and len(set(seen)) == 48


def test_no_filler_and_no_infinite_has_more_when_pool_is_similar():
    ranked = [outfit(f"o{i}", "same-trousers") for i in range(30)]
    page = select_diverse_outfits(ranked, [], 6)
    assert len(page["outfits"]) == 2
    assert not page["has_more"]
    assert page["diversity"]["stop_reason"] == "diversity_limit"
    assert not select_diverse_outfits(ranked, ["o0", "o1"], 6)["outfits"]


def test_recipe_spacing_and_exact_boundary_reconsider_deferred_candidates():
    ranked = [outfit("master", "m", "root"), outfit("variant", "v", "root")]
    ranked += [outfit(f"o{i}", f"g{i}") for i in range(15)]
    page = select_diverse_outfits(ranked, [], 12)
    ids = [o["outfit_id"] for o in page["outfits"]]
    assert ids.index("variant") == 8
    assert_constraints(page["outfits"])


def test_probe_does_not_skip_unseen_candidate_and_deterministic():
    ranked = [outfit(str(i), str(i)) for i in range(13)]
    a = select_diverse_outfits(ranked, [], 6)
    assert a == select_diverse_outfits(ranked, [], 6)
    b = select_diverse_outfits(ranked, [o["outfit_id"] for o in a["outfits"]], 6)
    assert b["outfits"][0]["outfit_id"] == "6"


def test_outer_and_dress_are_main_but_accessories_are_not():
    rows = [{"outfit_id": str(i), "items": [
        {"item_id": "coat", "slot": "outer", "category": "top"},
        {"item_id": "bag", "category": "bag"},
        {"item_id": f"dress{i}", "category": "dress"}]} for i in range(10)]
    assert len(select_diverse_outfits(rows, [], 6)["outfits"]) == 2


def test_families_require_current_visual_evidence_and_matching_category():
    records = [{"id": "a", "category": "top"}, {"id": "b", "category": "top"}]
    family = {"id": "f", "status": "visual_reviewed", "reviewer": "r", "evidence": "e",
              "members": {r["id"]: record_fingerprint(r) for r in records}}
    registry = {"families": [family]}
    assert style_family_map(records, registry) == {"a": "f", "b": "f"}
    family["status"] = "candidate"
    assert style_family_map(records, registry) == {}
    family["status"] = "visual_reviewed"
    records[0]["new_revision"] = True
    assert style_family_map(records, registry) == {}


def test_malformed_registry_falls_back_to_singletons():
    for value in ([], {"families": None}, {"families": [None, {"id": "bad", "members": None}]}):
        assert style_family_map([], value) == {}


def test_family_withdrawal_with_preserved_mtime_is_not_cached(tmp_path, monkeypatch):
    from app import recommendation_diversity as module

    records = [{"id": "a", "category": "top"}, {"id": "b", "category": "top"}]
    family = {"id": "f", "status": "visual_reviewed", "reviewer": "r", "evidence": "e",
              "members": {r["id"]: record_fingerprint(r) for r in records}}
    registry = {"schema_version": 1, "families": [family]}
    path = tmp_path / "families.json"
    path.write_text(json.dumps(registry))
    monkeypatch.setattr(module, "FAMILY_PATH", path)
    assert style_family_map(records) == {"a": "f", "b": "f"}
    stamp = path.stat()
    family["status"] = "needs_review"
    path.write_text(json.dumps(registry))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert style_family_map(records) == {}
    # Malformed bytes and missing files must also revoke, not reuse, old data.
    path.write_bytes(b"\xff")
    assert style_family_map(records) == {}
    path.unlink()
    assert style_family_map(records) == {}


def test_home_first_viewport_and_following_pages_separate_shared_main_items():
    rows = [outfit('first', 'floral-skirt'), outfit('similar', 'floral-skirt')]
    rows += [outfit(f'other{i}', f'garment{i}') for i in range(20)]
    first = select_diverse_outfits(rows, [], 10, home_surface=True)
    ids = [o['outfit_id'] for o in first['outfits']]
    assert ids[0] == 'first'
    assert 'similar' not in ids
    second = select_diverse_outfits(rows, ids, 6, home_surface=True)
    assert second['outfits'][0]['outfit_id'] == 'similar'


def test_home_different_ids_in_same_reviewed_family_are_spaced():
    rows = [outfit('a', 'skirt-a', family='floral'), outfit('b', 'skirt-b', family='floral')]
    rows += [outfit(str(i), str(i)) for i in range(12)]
    page = select_diverse_outfits(rows, [], 10, home_surface=True)
    assert len(page['outfits']) == 10
    assert 'b' not in [o['outfit_id'] for o in page['outfits']]


def test_home_shared_accessories_do_not_hide_distinct_main_garments():
    rows = [outfit(str(i), str(i)) for i in range(10)]
    for row in rows:
        row['items'].append({'item_id': 'shared-bag', 'category': 'bag'})
    assert len(select_diverse_outfits(rows, [], 10, home_surface=True)['outfits']) == 10

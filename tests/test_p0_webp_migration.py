from scripts import migrate_selfit_p0_selected_assets_to_webp as migration


def test_recursive_rewrite_updates_only_exact_bound_values():
    value = {"path": "old.png", "sha": "abc", "nested": ["old.png", "prefix-old.png"]}
    assert migration.replace_strings(value, {"old.png": "new.webp", "abc": "def"}) == {
        "path": "new.webp", "sha": "def", "nested": ["new.webp", "prefix-old.png"]}


def test_current_migration_audit_proves_selected_assets_are_webp():
    path = migration.ROOT / "docs/audits/20260904-p0-acceptance/p0-selected-webp-migration.v1.json"
    result = __import__("json").loads(path.read_text())
    assert len(result["conversions"]) == 25
    assert all(row["lossless_pixel_equal"] for row in result["conversions"])
    assert all(row["source_retained_for_audit"] for row in result["conversions"])
    assert result["selected_asset_audit"] == {
        "anchor_count": 160,
        "unique_asset_urls": 452,
        "formats": {"WEBP": 452},
        "missing": [],
        "non_webp": [],
        "all_webp": True,
    }

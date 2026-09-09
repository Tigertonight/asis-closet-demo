from app import closet, storage


def test_new_users_receive_one_white_tee_without_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    for user_id in ("first-visitor", "first-signed-in-user"):
        with storage.user_storage(user_id):
            first = closet.list_closet_items()
            assert first["total"] == 1
            tee = first["items"][0]
            assert tee["title"] == "白 T" and tee["category"] == "top"
            assert tee["is_default"] and tee["user_id"] == user_id
            assert (closet.ROOT_DIR / "app" / tee["assets"]["cutout_path"].lstrip("/")).is_file()
            assert closet.list_closet_items() == first
            closet._write_manifest({"version": 1, "items": first["items"]})
            assert closet.list_closet_items() == first


def test_default_edits_existing_items_and_deletions_are_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    with storage.user_storage("existing-user"):
        tee = closet.list_closet_items()["items"][0]
        tee["title"] = "我常穿的白 T"
        existing = {"item_id": "saved-jeans", "title": "我的牛仔裤", "category": "bottom", "deleted": False}
        closet._write_manifest({"version": 1, "items": [tee, existing]})
        assert closet.list_closet_items()["total"] == 2
        assert closet.get_closet_item(tee["item_id"])["title"] == "我常穿的白 T"
        closet.delete_closet_item(tee["item_id"])
        for _ in range(2):
            assert closet.list_closet_items()["items"] == [existing]

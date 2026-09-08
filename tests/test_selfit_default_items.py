from PIL import Image
from app import closet, storage, selfit_studio


def test_defaults_are_available_for_each_persona_and_generate_outfit(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    personas = ['mute','iced','heir','ease','melt','wabi','flou','neon','edge','bolt','film','jade','loop','noir','void','oops']
    ids = None
    for persona in personas:
        with storage.user_storage('test_' + persona):
            rows = selfit_studio.personal_wardrobe()['items']
            assert len(rows) == 3
            current = {x['item_id'] for x in rows}
            assert ids is None or current == ids
            ids = current
            for row in rows:
                with Image.open(closet._closet_disk_path(row['assets']['cutout_path'])) as image:
                    assert image.mode == 'RGBA'
                    assert image.getchannel('A').getextrema() == (0, 255)
    with storage.user_storage('test_loop'):
        outfit = closet.create_outfit({'item_ids': list(ids), 'title': '基础搭配'})
        assert len(outfit['items']) == 3
        assert closet._closet_disk_path(outfit['cover_path']).is_file()
        deleted = next(iter(ids))
        closet.delete_closet_item(deleted)
        assert len(closet.list_closet_items()['items']) == 2
        assert len(closet.list_closet_items()['items']) == 2
    with storage.user_storage('test_melt'):
        assert len(closet.list_closet_items()['items']) == 3

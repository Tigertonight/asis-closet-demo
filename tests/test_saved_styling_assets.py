from copy import deepcopy

from PIL import Image

from app import closet, storage, styling_catalog
from app.material_assets import asset_content_url


OLD = 'asset_' + 'a' * 64
NEW = 'asset_' + 'b' * 64


def saved_item():
    return {
        'item_id': 'saved-original-id', 'image_id': OLD, 'title': '我改过的标题',
        'category': 'top', 'slot': 'outer', 'display_order': 3, 'favorite': True,
        'source': {'type': 'styling_delivery', 'source_item_id': 'notebook-piece'},
        'assets': {'asset_id': OLD, 'cutout_path': asset_content_url(OLD), 'preview_path': asset_content_url(OLD)},
        'wearing_instruction': '搭在肩上', 'styling': {'paired_with_item_ids': ['personal-shirt']},
    }


def catalog(monkeypatch):
    monkeypatch.setattr(styling_catalog, 'delivery_looks', lambda: [{'items': [
        {'item_id': 'notebook-piece', 'image_asset': {'assetId': NEW, 'sourceAssetId': OLD}},
    ]}])
    monkeypatch.setattr(styling_catalog.MaterialRegistry, 'get', lambda self, key: {'url': '/static/new.png'})


def test_upgrade_only_exact_source_mapping_preserving_saved_identity_and_edits(monkeypatch):
    catalog(monkeypatch)
    original = saved_item()
    before = deepcopy(original)
    upgraded = styling_catalog.resolve_saved_item_assets([original])[0]
    assert original == before
    assert upgraded['image_id'] == NEW
    assert upgraded['assets'] == {'asset_id': NEW, 'source_asset_id': OLD,
                                  'cutout_path': asset_content_url(NEW), 'preview_path': asset_content_url(NEW)}
    assert {k: v for k, v in upgraded.items() if k not in {'image_id', 'assets'}} == {
        k: v for k, v in original.items() if k not in {'image_id', 'assets'}
    }
    assert styling_catalog.resolve_saved_item_assets([upgraded]) == [upgraded]
    for field, value in [('type', 'upload'), ('source_item_id', 'different-piece')]:
        unrelated = deepcopy(original)
        unrelated['source'][field] = value
        assert styling_catalog.resolve_saved_item_assets([unrelated]) == [unrelated]
    edited_image = deepcopy(original)
    edited_image['assets']['asset_id'] = 'asset_' + 'c' * 64
    assert styling_catalog.resolve_saved_item_assets([edited_image]) == [edited_image]


def test_saved_outfit_and_tryon_resolve_transparency_without_resetting_layout(monkeypatch, tmp_path):
    catalog(monkeypatch)
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    monkeypatch.setattr(closet, '_with_default_items', lambda data: data)
    image = tmp_path / 'transparent.png'
    Image.new('RGBA', (32, 32), (255, 255, 255, 0)).save(image)
    seen = []
    def material_path(key):
        seen.append(key)
        return image
    monkeypatch.setattr('app.material_assets.material_image_path', material_path)
    with storage.user_storage('owner'):
        closet._write_manifest({'version': 1, 'items': [saved_item()]})
        old_bytes = closet._closet_manifest_path().read_bytes()
        outfit = {'outfit_id': 'saved-outfit', 'item_ids': ['saved-original-id'], 'favorite': True,
                  'layout_version': closet.OUTFIT_LAYOUT_VERSION, 'cover_path': str(image),
                  'layout_slots': [{'item_id': 'saved-original-id', 'x': 27, 'y': 41}],
                  'display_item_ids': ['saved-original-id']}
        closet._write_outfit_manifest({'version': 1, 'outfits': [outfit], 'plans': []})
        monkeypatch.setattr(closet, '_build_outfit_cover', lambda *a, **k: (_ for _ in ()).throw(AssertionError('keep layout')))
        item = closet.get_closet_item('saved-original-id')
        assert item['assets']['cutout_path'] == asset_content_url(NEW)
        loaded = closet.list_outfits()['outfits'][0]
        assert loaded['layout_slots'] == outfit['layout_slots']
        assert loaded['item_ids'] == outfit['item_ids'] and loaded['favorite'] is True
        plan, _ = closet.outfit_as_tryon_plan('saved-outfit')
        assert plan['items'][0]['image_id'] == NEW
        assert plan['items'][0]['public_image_path'] == asset_content_url(NEW)
        assert seen == [NEW]
        assert closet._closet_manifest_path().read_bytes() == old_bytes


def test_missing_catalog_or_unpublished_cutout_retains_saved_assets(monkeypatch):
    item = saved_item()
    catalog(monkeypatch)
    def unavailable(*args): raise KeyError('not published')
    monkeypatch.setattr(styling_catalog.MaterialRegistry, 'get', unavailable)
    assert styling_catalog.resolve_saved_item_assets([item]) == [item]
    monkeypatch.setattr(styling_catalog, 'delivery_looks', lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert styling_catalog.resolve_saved_item_assets([item]) == [item]

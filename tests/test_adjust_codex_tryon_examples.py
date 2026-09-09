from copy import deepcopy

from scripts import adjust_codex_tryon_examples as adjusted
from scripts import batch_codex_tryon_examples as batch


def test_covered_variant_does_not_mutate_source_or_drop_items():
    plan = {'title': 'look', 'items': [
        {'item_id': 'top1', 'slot': 'top', 'category_label': '蕾丝上衣', 'wearing_instruction': '原穿法'},
        {'item_id': 'bottom1', 'slot': 'bottom', 'category_label': '长裤', 'wearing_instruction': '坐姿'},
        {'item_id': 'socks1', 'slot': 'socks', 'category_label': '袜子', 'wearing_instruction': '原穿法'},
    ]}
    before = deepcopy(plan)
    variant, changes = adjusted.adjusted_plan(plan, 'flou')
    assert plan == before
    assert [x['item_id'] for x in variant['items']] == ['top1', 'bottom1', 'socks1']
    assert '完整不透内衬' in variant['items'][0]['wearing_instruction']
    assert '裤管闭合' in variant['items'][1]['wearing_instruction']
    assert changes


def test_loop_variant_resolves_coverage_and_bag_conflicts():
    plan = {'title': 'look', 'items': [
        {'item_id': 'skirt1', 'slot': 'skirt', 'category_label': '浅蓝斜襟裙', 'wearing_instruction': '原穿法'},
        {'item_id': 'socks1', 'slot': 'socks', 'category_label': '透肤袜', 'wearing_instruction': '原穿法'},
        {'item_id': 'bag1', 'slot': 'bag', 'category_label': '棕色肩包', 'wearing_instruction': '放台阶上'},
    ]}
    variant, _ = adjusted.adjusted_plan(plan, 'loop-curvy')
    assert '大腿中段' in variant['items'][0]['wearing_instruction']
    assert '不透明' in variant['items'][1]['wearing_instruction']
    assert '右肩' in variant['items'][2]['wearing_instruction']
    assert plan['items'][2]['wearing_instruction'] == '放台阶上'


def test_single_pass_patch_is_scoped_to_variant(monkeypatch):
    plan = {'items': [{'item_id': 'x', 'slot': 'top'}]}
    monkeypatch.setattr(adjusted, 'read', lambda path: plan)
    before = adjusted.tryon._outfit_generation_groups
    provider = batch.CodexEffectProvider
    with adjusted.generation_context({'adjustedPlanPath': 'variant.json'}):
        assert adjusted.tryon._outfit_generation_groups(plan) == [('complete_outfit', plan)]
        assert batch.CodexEffectProvider is adjusted.AdjustedProvider
    assert adjusted.tryon._outfit_generation_groups is before
    assert batch.CodexEffectProvider is provider

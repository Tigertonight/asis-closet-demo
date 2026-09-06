import pytest

from scripts.render_selfit_aw_designed_recipes import resolve_layer_graph, layout_items_for_layers


TOKENS = {"d": "dress", "j": "jacket", "c": "coat", "s": "shoe"}
ITEMS = [{"id": "dress", "category": "dress"}, {"id": "jacket", "category": "outer"},
         {"id": "shoe", "category": "shoes"}]


def test_preserves_explicit_dress_beneath_jacket():
    assert resolve_layer_graph({"layer_graph": [{"inner": "d", "outer": "j"}]}, TOKENS, ITEMS) == [
        {"inner": "dress", "outer": "jacket"}]


def test_unlayered_dress_needs_no_edges():
    assert resolve_layer_graph({}, TOKENS, [ITEMS[0], ITEMS[2]]) == []


@pytest.mark.parametrize("graph", [None, [], [{"inner": "d"}], [{"inner": "d", "outer": "s"}],
    [{"inner": "d", "outer": "c"}], [{"inner": "d", "outer": "d"}],
    [{"inner": "d", "outer": "j"}, {"inner": "d", "outer": "j"}],
    [{"inner": "d", "outer": "j"}, {"inner": "j", "outer": "d"}]])
def test_rejects_missing_invalid_or_cyclic_layer_order(graph):
    with pytest.raises(ValueError):
        resolve_layer_graph({"layer_graph": graph}, TOKENS, ITEMS)


def test_three_layers_require_connected_order():
    items = ITEMS + [{"id": "coat", "category": "outer"}]
    edges = [{"inner": "d", "outer": "j"}]
    with pytest.raises(ValueError):
        resolve_layer_graph({"layer_graph": edges}, TOKENS, items)
    edges.append({"inner": "j", "outer": "c"})
    assert len(resolve_layer_graph({"layer_graph": edges}, TOKENS, items)) == 2


def test_two_tops_use_explicit_display_roles_without_mutating_recipe():
    items = [{"id": "vest", "category": "top"}, {"id": "inner", "category": "top"}]
    result = layout_items_for_layers(items, [{"inner": "inner", "outer": "vest"}])
    assert result == [{"id": "vest", "category": "outer"}, {"id": "inner", "category": "top"}]
    assert all(item["category"] == "top" for item in items)
    reverse = layout_items_for_layers(items, [{"inner": "vest", "outer": "inner"}])
    assert reverse[0]["category"] == "top" and reverse[1]["category"] == "outer"


@pytest.mark.parametrize("graph", [[], [{"inner": "inner", "outer": "missing"}],
    [{"inner": "inner", "outer": "inner"}]])
def test_two_tops_cannot_infer_display_order(graph):
    with pytest.raises(ValueError):
        layout_items_for_layers([{"id": "vest", "category": "top"},
                                 {"id": "inner", "category": "top"}], graph)


def test_existing_dress_jacket_display_roles_are_unchanged():
    assert layout_items_for_layers(ITEMS, [{"inner": "dress", "outer": "jacket"}]) == ITEMS

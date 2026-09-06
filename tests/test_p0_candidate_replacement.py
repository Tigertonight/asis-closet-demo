from copy import deepcopy

import pytest

from scripts.stage_selfit_p0_replacement import add_slot, replace_slot


def fixture():
    catalog, anchors = {}, []
    for i in range(10):
        expression = "easy" if i < 4 else "typical" if i < 8 else "explore"
        structure = "pants" if i < 5 else "skirt"
        oid = f"o{i}"
        catalog[oid] = {"outfit_id": oid, "parent_outfit_id": oid, "primary_persona": "WABI",
            "visual": {"expression": expression, "structure": structure},
            "items": [{"item_id": f"g{i}", "category": "bottom"}]}
        anchors.append({"outfit_id": oid, "persona": "wabi", "expression": expression,
                        "structure": structure, "four_gate_current": False})
    candidate = {"outfit_id": "new", "parent_outfit_id": "new-main", "primary_persona": "WABI",
        "visual": {"expression": "explore", "structure": "dress"},
        "items": [{"item_id": "new-dress", "category": "dress"}]}
    return anchors, catalog, candidate


def test_replacement_resolves_structure_without_approving_or_mutating_source():
    anchors, catalog, candidate = fixture()
    before = deepcopy(anchors)
    result = replace_slot(anchors, catalog, {"id": "new"}, "o9", candidate, "素裙与外搭")
    assert anchors == before
    assert len(result) == 10
    assert result[-1]["structure"] == "dress"
    assert result[-1]["four_gate_current"] is False
    assert result[-1]["record_fingerprint"]


@pytest.mark.parametrize("case", ["missing_target", "wrong_persona", "wrong_expression", "same_recipe",
                                   "same_parent", "missing_structure", "family_cap"])
def test_replacement_rejects_constraint_violations(case):
    anchors, catalog, candidate = fixture()
    target = "missing" if case == "missing_target" else "o9"
    if case == "wrong_persona":
        candidate["primary_persona"] = "VOID"
    if case == "wrong_expression":
        candidate["visual"]["expression"] = "easy"
    if case == "same_recipe":
        candidate["items"] = deepcopy(catalog["o0"]["items"])
    if case == "same_parent":
        candidate["parent_outfit_id"] = "o0"
    if case == "missing_structure":
        candidate["visual"]["structure"] = "skirt"
    if case == "family_cap":
        for row in (catalog["o0"], catalog["o1"], candidate):
            row["items"][0]["style_family_id"] = "same-family"
    with pytest.raises(ValueError):
        replace_slot(anchors, catalog, {"id": "new"}, target, candidate, "新候选")


def test_addition_fills_partial_persona_without_approval():
    anchors, catalog, candidate = fixture()
    result = add_slot(anchors[:8], catalog, {"id": "new"}, candidate, "新候选")
    assert len(result) == 9
    assert result[-1]["four_gate_current"] is False
    assert len(anchors) == 10


@pytest.mark.parametrize("case", ["full", "expression_full", "duplicate", "parent", "structure_cap", "family_cap", "impossible_coverage"])
def test_addition_rejects_quota_or_diversity_violation(case):
    anchors, catalog, candidate = fixture()
    selected = anchors[:8]
    if case == "full":
        selected = anchors
    if case == "expression_full":
        candidate["visual"]["expression"] = "easy"
    if case == "duplicate":
        candidate["items"] = deepcopy(catalog["o0"]["items"])
    if case == "parent":
        candidate["parent_outfit_id"] = "o0"
    if case == "structure_cap":
        candidate["visual"]["structure"] = "pants"
    if case == "family_cap":
        for row in (catalog["o0"], catalog["o1"], candidate):
            row["items"][0]["style_family_id"] = "same"
    if case == "impossible_coverage":
        selected = anchors[:9]
        candidate["visual"]["structure"] = "skirt"
    with pytest.raises(ValueError):
        add_slot(selected, catalog, {"id": "new"}, candidate, "新候选")

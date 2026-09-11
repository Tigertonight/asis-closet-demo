"""Published white-tee compositions must never reuse the original-shirt image."""
from copy import deepcopy
import json

import pytest

from app import auth, closet, storage, tryon, white_tee_presets as white, selfit_tryon_presets as presets
from app.selfit_studio import StudioOutfit, save_studio_outfit
from app.styling_catalog import adapt_outfit


def model_bytes(row):
    from app.material_assets import material_image_path
    model = row["model"]
    path = material_image_path(model["image_asset_id"]) if model.get("image_asset_id") else white.ROOT / model["localPath"]
    return path.read_bytes()


@pytest.fixture
def recipe_case(tmp_path, monkeypatch):
    source = json.loads(white.INDEX.read_text())
    row = deepcopy(source["examples"][0])
    candidates = white.recipes()
    recipe = next(r for r in candidates if r["key"] == row["key"])
    monkeypatch.setattr(white, "recipes", lambda: deepcopy(candidates))
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"examples": [row]}))
    monkeypatch.setattr(white, "INDEX", path)
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path / "users")
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "auth")
    # Fixtures use published bytes/asset records, but never make network calls.
    from app import material_assets
    raw = model_bytes(row)
    monkeypatch.setattr(material_assets, "material_download_url", lambda record: "/verified.png")
    with storage.user_storage("white-tee-preset-owner"):
        outfit = save_studio_outfit(StudioOutfit(item_ids=recipe["outfit"]["item_ids"]))
        yield row, recipe, outfit, raw, path


def test_saved_recipe_hits_preset_and_original_does_not(recipe_case):
    row, recipe, outfit, raw, _ = recipe_case
    assert not outfit["outfit_id"].startswith("report_")
    result = presets.find_preset(outfit["outfit_id"], row["modelId"], raw, outfit["item_ids"])
    assert result and result["example_id"] == row["id"]
    assert result["outfit"]["outfit_id"] == outfit["outfit_id"]
    assert result["image_path"] == row["result"]["contentUrl"]
    original = adapt_outfit(recipe["look"])
    assert white.find_white_tee_preset(original["outfit_id"], row["modelId"], raw, original["item_ids"]) is None
    with storage.user_storage("someone-else"):
        assert presets.find_preset(outfit["outfit_id"], row["modelId"], raw, outfit["item_ids"]) is None


@pytest.mark.parametrize("case", ["partial", "different_photo", "self", "female_model", "modified_tee", "modified_item",
                                  "modified_wearing", "modified_slot", "old_recipe", "failed", "unverified",
                                  "failed_quality", "stale_visual_review", "duplicate"])
def test_changed_inputs_fall_back(recipe_case, monkeypatch, case):
    row, recipe, outfit, raw, path = recipe_case
    model = row["modelId"]; ids = outfit["item_ids"]
    if case == "partial": ids = ids[:-1]
    if case == "different_photo": raw += b"changed"
    if case == "self": model = "self"
    if case == "female_model": model = "female_medium_1"
    changed = deepcopy(outfit)
    if case == "modified_tee":
        next(i for i in changed["items"] if i["item_id"] == white.anchor_item()["item_id"])["assets"]["cutout_path"] = "/static/another-tee.png"
    if case == "modified_item": changed["items"][-1]["image_id"] = "another-image"
    if case == "modified_wearing": changed["items"][-1]["wearing_instruction"] = "different attachment"
    if case == "modified_slot": changed["items"][-1]["slot"] = "hat"
    monkeypatch.setattr(closet, "get_outfit", lambda key: changed)
    if case == "old_recipe": row["recipeFingerprint"] = "old"
    if case == "failed": row["status"] = "failed_quality"
    if case == "unverified": row["result"]["verified"] = False
    if case == "failed_quality": row["qualityReview"]["status"] = "fail"
    if case == "stale_visual_review": row["visualReview"]["resultSha256"] = "old-image"
    path.write_text(json.dumps({"examples": [row, row] if case == "duplicate" else [row]}))
    assert presets.find_preset(outfit["outfit_id"], model, raw, ids) is None


def test_white_tee_job_records_history_without_worker(recipe_case, monkeypatch):
    row, _, outfit, raw, _ = recipe_case
    class Executor:
        def submit(self, *args):
            raise AssertionError("A matching preset must not call image generation")
    monkeypatch.setattr(tryon, "TRYON_JOB_EXECUTOR", Executor())
    job = tryon.create_outfit_tryon_job(raw, row["model"]["file"], outfit["outfit_id"], "standard", "",
                                       "white-tee-preset-owner", selected_item_ids=outfit["item_ids"],
                                       client_request_id="white-tee-preset-test", wear_all_items=True, model_id=row["modelId"])
    assert job["status"] == "completed"
    assert job["result"]["preset_id"] == row["id"]
    assert job["result"]["generation_strategy"] == "preset"
    assert job["result"]["record"]["outfit_id"] == outfit["outfit_id"]
    assert job["result"]["requested_item_ids"] == outfit["item_ids"]


def test_recipe_deduplication_keeps_male_inner_layer():
    recipes = white.recipes()
    male = [r for r in recipes if r["gender"] == "male"]
    assert len(male) == 12
    assert len({r["key"] for r in recipes}) == len(recipes)
    edge = next(r for r in male if r["look"]["note_binding"]["templateId"] == "edge-male" and r["look"]["note_binding"]["noteId"] == "outfits-04")
    assert len(edge["outfit"]["items"]) == len(edge["look"]["items"])
    assert sum(i["slot"] == "top" for i in edge["outfit"]["items"]) == 2
    assert edge["outfit"]["items"][0]["item_id"] == white.anchor_item()["item_id"]


def test_all_male_recipes_are_published_and_resolve_after_saving(tmp_path, monkeypatch):
    """Exercise every real saved composition, including layered and accessory looks."""
    from app import material_assets
    source = json.loads(white.INDEX.read_text())
    candidates = white.recipes()
    male = {r["key"]: r for r in candidates if r["gender"] == "male"}
    rows = [r for r in source["examples"] if r["gender"] == "male"]
    assert source["countsByGender"]["male"] == {"expected": 12, "uploaded": 12}
    assert len(rows) == 12 and {r["key"] for r in rows} == set(male)
    assert {r["modelId"] for r in rows} == {"male_standard_1"}
    monkeypatch.setattr(white, "recipes", lambda: deepcopy(candidates))
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path / "users")
    model_raw = {r["modelId"]: model_bytes(r) for r in rows}
    monkeypatch.setattr(material_assets, "material_download_url", lambda record: "/verified.png")
    with storage.user_storage("white-tee-batch-owner"):
        for row in rows:
            outfit = save_studio_outfit(StudioOutfit(item_ids=male[row["key"]]["outfit"]["item_ids"]))
            raw = model_raw[row["modelId"]]
            hit = presets.find_preset(outfit["outfit_id"], row["modelId"], raw, outfit["item_ids"])
            assert hit and hit["example_id"] == row["id"]
            assert hit["image_path"] == row["result"]["contentUrl"]


@pytest.mark.parametrize("model", ["female_slim_1", "female_medium_1", "female_plus_1"])
def test_female_saved_white_tee_requires_current_photo_then_records_history(tmp_path, monkeypatch, model):
    from app import material_assets
    source = json.loads(white.INDEX.read_text())
    row = next(r for r in source["examples"] if r["modelId"] == model)
    candidates = white.recipes()
    recipe = next(r for r in candidates if r["key"] == row["key"])
    assert recipe["gender"] == "female"
    monkeypatch.setattr(white, "recipes", lambda: deepcopy(candidates))
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path / "users")
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "auth")
    raw = model_bytes(row)
    monkeypatch.setattr(material_assets, "material_download_url", lambda record: "/verified.png")
    class NoGenerator:
        def submit(self, *args):
            raise AssertionError("Published female white-tee recipe must not generate")
    monkeypatch.setattr(tryon, "TRYON_JOB_EXECUTOR", NoGenerator())
    with storage.user_storage("female-white-tee-owner"):
        outfit = save_studio_outfit(StudioOutfit(item_ids=recipe["outfit"]["item_ids"]))
        import hashlib
        if hashlib.sha256(raw).hexdigest() != row["model"]["sha256"]:
            # Unpublished local originals are intentionally absent in a fresh
            # checkout. Its shared model must reject the local-model preset.
            assert presets.find_preset(outfit["outfit_id"], model, raw, outfit["item_ids"]) is None
            return
        job = tryon.create_outfit_tryon_job(raw, row["model"]["file"], outfit["outfit_id"], "standard", "",
                                          "female-white-tee-owner", selected_item_ids=outfit["item_ids"],
                                          client_request_id="female-white-tee-" + model, wear_all_items=True, model_id=model)
        assert job["status"] == "completed"
        assert job["result"]["preset_id"] == row["id"]
        assert job["result"]["record"]["image_path"] == row["result"]["contentUrl"]
        assert any(r["record_id"] == job["result"]["record"]["record_id"] for r in closet.list_tryon_records()["records"])
        assert presets.find_preset(outfit["outfit_id"], "male_standard_1", raw, outfit["item_ids"]) is None
        assert presets.find_preset(outfit["outfit_id"], model, raw + b"changed", outfit["item_ids"]) is None

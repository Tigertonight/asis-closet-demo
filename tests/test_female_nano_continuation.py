import base64
from copy import deepcopy
import hashlib
import json

from PIL import Image
import pytest

from scripts import batch_female_nano_presets as batch


@pytest.fixture
def prior_turn(monkeypatch, tmp_path):
    Image.init()
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    monkeypatch.setattr(batch, "BATCH", tmp_path / "batch")
    monkeypatch.setattr(batch.vertex_image, "model", lambda: "gemini-3.1-flash-image")
    folder = tmp_path / "job/attempts/01"
    folder.mkdir(parents=True)
    for name, color in (("original", "white"), ("item", "red"), ("native", "gray")):
        Image.new("RGB", (30, 40), color).save(folder / (name + ".png"))
    original = folder / "original.png"
    native = folder / "native.png"
    digest = batch.sha(native)
    request = {"model": "gemini-3.1-flash-image", "images": [
        batch.image_ref(original, "IMAGE 1 original"),
        batch.image_ref(folder / "item.png", "IMAGE 2 item", ["item-1"])],
        "promptSha256": hashlib.sha256(b"original request").hexdigest()}
    request["requestId"] = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    batch.write_json_atomic(folder / "request.json", request)
    catalog_path = batch.BATCH / "catalog/look-1/catalog.json"
    catalog_path.parent.mkdir(parents=True)
    batch.write_json_atomic(catalog_path, {"outfitId": "outfit-1", "look": {"items": [{"item_id": "delivery-item-1"}]},
                                          "references": request["images"][1:]})
    (folder / "prompt.txt").write_text("original request")
    content = {"role": "model", "parts": [{"inlineData": {
        "mimeType": "image/png", "data": base64.b64encode(native.read_bytes()).decode()}, "thoughtSignature": "opaque-native-signature"}]}
    receipt = batch.save_private_continuation({"candidates": [{"content": content}]}, folder)
    attempt = {"path": "job/attempts/01", "requestId": request["requestId"], "nativePath": "job/attempts/01/native.png",
               "nativeSha256": digest, "continuationResponse": receipt, "qualityReview": {"status": "pass"},
               "result": {"localPath": "job/attempts/01/native.png", "sha256": digest},
               "visualReview": {"status": "fail", "modelId": "model-1", "key": "look-1", "resultSha256": digest,
                                "observations": "button open", "reviewedAt": "viewed"}}
    row = {"id": "model-1--look-1", "modelId": "model-1", "key": "look-1", "status": "failed_visual",
           "outfitId": "outfit-1", "model": {"sha256": batch.sha(original)}, "itemIds": ["delivery-item-1"], "generationModel": request["model"],
           "retryCorrection": "close button", "retryOutfitReference": {"attemptPath": attempt["path"], "sha256": digest},
           "attempts": [attempt]}
    return row, content, folder


def test_native_continuation_preserves_exact_parts_and_all_initial_inputs(prior_turn):
    row, content, folder = prior_turn
    result = batch.reviewed_conversation_request(row, "close button")
    assert [c["role"] for c in result["contents"]] == ["user", "model", "user"]
    assert result["contents"][1] == content
    initial = result["contents"][0]["parts"]
    assert base64.b64decode(initial[1]["inlineData"]["data"]) == (folder / "original.png").read_bytes()
    assert base64.b64decode(initial[3]["inlineData"]["data"]) == (folder / "item.png").read_bytes()
    assert initial[-1] == {"text": "original request"}
    assert "close button" in result["contents"][-1]["parts"][0]["text"]
    assert result["metadata"]["contentsSha256"] == hashlib.sha256(json.dumps(result["contents"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert "opaque-native-signature" not in str(result["metadata"])


def test_native_continuation_rejects_different_job_or_model_or_changed_input(prior_turn):
    row, _, folder = prior_turn
    wrong = deepcopy(row)
    wrong["modelId"] = "other-model"
    with pytest.raises(ValueError):
        batch.reviewed_conversation_request(wrong, "close button")
    wrong = deepcopy(row)
    wrong["generationModel"] = "another-provider-model"
    with pytest.raises(ValueError):
        batch.reviewed_conversation_request(wrong, "close button")
    (folder / "item.png").write_bytes(b"changed")
    with pytest.raises(ValueError):
        batch.reviewed_conversation_request(row, "close button")


def test_native_continuation_rejects_forged_response_and_missing_signature(prior_turn):
    row, content, folder = prior_turn
    (folder / "continuation-response.json").write_text("{}")
    with pytest.raises(ValueError):
        batch.reviewed_conversation_request(row, "close button")
    del content["parts"][0]["thoughtSignature"]
    row["attempts"][0]["continuationResponse"] = batch.save_private_continuation({"candidates": [{"content": content}]}, folder)
    with pytest.raises(ValueError):
        batch.reviewed_conversation_request(row, "close button")


def test_retired_notes_stay_out_of_retry_queue_without_changing_the_snapshot(monkeypatch, tmp_path):
    kept = {'note_binding': {'templateId': 'inspiration_date', 'noteId': 'outfits-01'}}
    retired = {'note_binding': {'templateId': 'inspiration_date', 'noteId': 'outfits-04'}}
    monkeypatch.setattr(batch, 'BATCH', tmp_path)
    monkeypatch.setattr(batch, 'looks', lambda: [kept])
    snapshot = tmp_path / 'source-snapshot.json'
    snapshot.write_text(json.dumps({'looks': [kept, retired]}))
    before = snapshot.read_bytes()
    assert batch.job_paths() == [tmp_path / mid / 'inspiration_date--outfits-01' / 'job.json' for mid in batch.MODEL_IDS]
    assert snapshot.read_bytes() == before
    monkeypatch.setattr(batch, 'looks', lambda: [{**kept, 'source_asset': {'assetId': 'changed'}}])
    with pytest.raises(ValueError, match='snapshot'):
        batch.job_paths()

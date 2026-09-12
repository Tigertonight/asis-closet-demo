from scripts.batch_female_nano_presets import garment_only_context, prompt_for


def test_candidate_edit_has_one_base_and_retains_original_identity_and_item_authorities():
    catalog = {"plan": {"title": "近完成套装"}, "itemContext": [
        {"name": "上衣", "reference": "IMAGE 3", "wearing_method": "最上方纽扣扣合"},
        {"name": "戒指", "reference": "IMAGE 4", "wearing_method": "只有一枚"}]}
    prompt = prompt_for(catalog, "remove the duplicate ring", reviewed_candidate=True)
    assert "Edit Image 2" in prompt and "by editing Image 1" not in prompt
    assert "clothing layering and wearing relationships ONLY" not in prompt
    assert "Image 1 is the sole authority" in prompt
    assert "Image 1 overrides Image 2" in prompt
    assert "IMAGE 3" in prompt and "IMAGE 4" in prompt
    assert "最上方纽扣扣合" in prompt and "只有一枚" in prompt
    assert "remove the duplicate ring" in prompt
    original = prompt_for(catalog)
    assert "by editing Image 1" in original and "Edit Image 2" not in original


def test_reviewed_outfit_reference_requires_same_job_numeric_pass_and_hash_bound_failure(monkeypatch, tmp_path):
    from copy import deepcopy
    from PIL import Image
    import pytest
    from scripts import batch_female_nano_presets as batch
    source = tmp_path / "result.png"
    Image.new("RGB", (20, 30), "white").save(source)
    digest = batch.sha(source)
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    row = {"id": "medium--look", "modelId": "medium", "key": "look", "status": "failed_visual",
           "retryCorrection": "restore the missing necklace", "retryOutfitReference": {"attemptPath": "attempts/02", "sha256": digest},
           "attempts": [{"path": "attempts/02", "result": {"localPath": "result.png", "sha256": digest},
                         "qualityReview": {"status": "pass"},
                         "visualReview": {"status": "fail", "modelId": "medium", "key": "look",
                                          "resultSha256": digest, "observations": "missing necklace", "reviewedAt": "viewed"}}]}
    original = deepcopy(row)
    ref = batch.reviewed_outfit_reference(row)
    assert ref["sha256"] == digest and ref["derivation"]["jobId"] == row["id"]
    assert row == original and batch.sha(source) == digest
    for field, value in [("modelId", "another-model"), ("key", "another-outfit"), ("resultSha256", "stale"), ("status", "pass")]:
        changed = deepcopy(row)
        changed["attempts"][0]["visualReview"][field] = value
        with pytest.raises(ValueError):
            batch.reviewed_outfit_reference(changed)
    row["attempts"][0]["qualityReview"]["status"] = "fail"
    with pytest.raises(ValueError):
        batch.reviewed_outfit_reference(row)
    row = deepcopy(original)
    row["status"] = "blocked_moderation"
    with pytest.raises(ValueError):
        batch.reviewed_outfit_reference(row)
    Image.new("RGB", (20, 30), "black").save(source)
    with pytest.raises(ValueError):
        batch.reviewed_outfit_reference(original)


def test_documented_item_correction_preserves_catalog_and_reference_binding():
    from copy import deepcopy
    from scripts.batch_female_nano_presets import request_item_context
    catalog = {"plan": {"title": "短胸门襟"}, "itemContext": [
        {"name": "薄荷上衣", "reference": "IMAGE 3", "slot": "top", "wearing_method": "全长开衫腰腹扣合"},
        {"name": "项链", "reference": "IMAGE 4", "wearing_method": "短链圆环吊坠"}]}
    original = deepcopy(catalog)
    changes = [{"name": "薄荷上衣", "reason": "Full original and isolated item show a short chest placket.",
                "fields": {"wearing_method": "短胸门襟，腹部连续面料，衣摆外放"}}]
    items = request_item_context(catalog, changes)
    assert items[0]["reference"] == "IMAGE 3" and items[0]["slot"] == "top"
    assert items[1] == original["itemContext"][1]
    prompt = prompt_for(catalog, item_overrides=changes)
    assert "短胸门襟，腹部连续面料，衣摆外放" in prompt
    assert "全长开衫腰腹扣合" not in prompt
    assert catalog == original


def test_item_correction_rejects_unknown_items_reference_changes_and_missing_evidence():
    import pytest
    from scripts.batch_female_nano_presets import request_item_context
    catalog = {"itemContext": [{"name": "上衣", "reference": "IMAGE 3"}]}
    for change in [
        {"name": "不存在", "reason": "viewed", "fields": {"wearing_method": "外放"}},
        {"name": "上衣", "reason": "viewed", "fields": {"reference": "IMAGE 9"}},
        {"name": "上衣", "fields": {"wearing_method": "外放"}},
    ]:
        with pytest.raises(ValueError):
            request_item_context(catalog, [change])


def test_outfit_pose_notes_cannot_override_fixed_selfie_pose():
    items = [{"name": "白色半身裙", "wearing_method": "高腰穿着，双手插入前侧贴袋。",
              "visible_details": ["双手插入前侧贴袋", "裙身直筒垂落至膝下", "贴袋朝外"]},
             {"name": "白色手套", "wearing_method": "手套佩戴至前臂，袖口盖住手套上缘。"},
             {"name": "手提包", "wearing_method": "用下垂手提握包柄"}]
    cleaned = garment_only_context(items)
    assert "双手插入" not in str(cleaned)
    assert cleaned[0]["visible_details"] == ["裙身直筒垂落至膝下", "贴袋朝外"]
    assert "高腰穿着" in cleaned[0]["wearing_method"]
    assert cleaned[1:] == items[1:]
    assert "双手插入" in str(items), "Source descriptions must remain intact"
    prompt = prompt_for({"plan": {"title": "测试"}, "itemContext": items})
    assert "双手插入" not in prompt
    assert prompt.index("FINAL POSE LOCK") > prompt.index("白色半身裙")


def test_seated_and_two_hand_source_pose_preserves_garment_structure():
    items = [{"name": "针织长裙", "wearing_method": "单穿贴身长裙，坐姿下裙摆铺在腿部与地面"},
             {"name": "风衣", "visible_details": ["双手置于侧袋", "翻领自然展开"]},
             {"name": "交叠针织衫", "visible_details": ["前身交叉边线", "V 形领口"]},
             {"name": "托特包", "wearing_method": "双手提拎于身前"},
             {"name": "凉鞋", "visible_details": ["足背交叉细带", "踝带扣合"]}]
    cleaned = garment_only_context(items)
    assert cleaned[0]["wearing_method"] == "单穿贴身长裙，"
    assert cleaned[1]["visible_details"] == ["翻领自然展开"]
    assert cleaned[2] == items[2]
    assert cleaned[3]["wearing_method"] == "由原本下垂的非持手机手提握包柄"
    assert cleaned[4] == items[4]
    assert items[0]["wearing_method"].endswith("坐姿下裙摆铺在腿部与地面")


def test_resume_can_bound_new_requests_without_repeating_completed_jobs(monkeypatch, tmp_path):
    from scripts import batch_female_nano_presets as batch
    rows = {
        tmp_path / "old.json": {"status": "failed_quality", "attempts": [{}] * 5},
        tmp_path / "new.json": {"status": "queued", "attempts": []},
        tmp_path / "capped.json": {"status": "failed_api", "attempts": [{}] * 6},
        tmp_path / "done.json": {"status": "uploaded", "attempts": [{}]},
        tmp_path / "review.json": {"status": "generated_local", "attempts": [{}]},
        tmp_path / "blocked.json": {"status": "blocked_moderation", "attempts": [{}]},
    }
    calls = []
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch, "job_paths", lambda: list(rows))
    monkeypatch.setattr(batch, "read", lambda p: rows[p])
    monkeypatch.setattr(batch, "worker", lambda p, cap: calls.append((p.name, cap)))
    monkeypatch.setattr(batch, "status", lambda: {})
    monkeypatch.setattr(batch, "emit", lambda value: None)
    batch.run(1, 6, max_additional_attempts=1)
    assert calls == [("old.json", 6), ("new.json", 1)]


def test_resume_request_budget_still_honors_stop(monkeypatch, tmp_path):
    from scripts import batch_female_nano_presets as batch
    (tmp_path / "STOP").write_text("user pause")
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch, "status", lambda: {"dispatchPaused": True})
    monkeypatch.setattr(batch, "emit", lambda value: None)
    monkeypatch.setattr(batch, "job_paths", lambda: (_ for _ in ()).throw(AssertionError("must not dispatch")))
    assert batch.run(1, 6, max_additional_attempts=1) == {"dispatchPaused": True}


def test_api_first_respects_caps_reviewed_jobs_and_run_limit(monkeypatch, tmp_path):
    from scripts import batch_female_nano_presets as batch
    rows = {
        tmp_path / "quality.json": {"status": "failed_quality", "attempts": [{}] * 3},
        tmp_path / "queued.json": {"status": "queued", "attempts": []},
        tmp_path / "api.json": {"status": "failed_api", "attempts": [{}] * 2},
        tmp_path / "capped.json": {"status": "failed_api", "attempts": [{}] * 6},
        tmp_path / "reviewed.json": {"status": "reviewed", "attempts": [{}]},
        tmp_path / "blocked.json": {"status": "blocked_moderation", "attempts": [{}]},
    }
    calls = []
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch, "job_paths", lambda: list(rows))
    monkeypatch.setattr(batch, "read", lambda p: rows[p])
    monkeypatch.setattr(batch, "worker", lambda p, cap: calls.append((p.name, cap)))
    monkeypatch.setattr(batch, "status", lambda: {})
    monkeypatch.setattr(batch, "emit", lambda value: None)
    batch.run(1, 6, limit=2, max_additional_attempts=1, api_first=True)
    assert calls == [("api.json", 3), ("quality.json", 4)]


def test_identity_detail_is_lossless_and_bound_to_original_model(tmp_path):
    import pytest
    from PIL import Image
    from scripts.batch_female_nano_presets import identity_detail_reference, sha
    original = Image.new("RGB", (1792, 2400), "white")
    original.paste((12, 34, 56), (760, 160, 1120, 540))
    model = tmp_path / "model.png"
    original.save(model)
    digest = sha(model)
    ref = identity_detail_reference(model, digest, tmp_path, 10)
    assert ref["derivation"]["sourceSha256"] == digest
    assert ref["derivation"]["cropBox"] == [760, 160, 1120, 540]
    with Image.open(ref["path"]) as detail:
        assert detail.size == (360, 380)
        assert detail.tobytes() == original.crop((760, 160, 1120, 540)).tobytes()
    assert sha(model) == digest
    with pytest.raises(AssertionError):
        identity_detail_reference(model, "changed-model", tmp_path, 10)


def test_service_cooldown_applies_to_next_new_job_and_preserves_stop(monkeypatch, tmp_path):
    from scripts import batch_female_nano_presets as batch
    clock = [1000.0]
    sleeps = []
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch.time, "time", lambda: clock[0])
    monkeypatch.setattr(batch, "emit", lambda value: None)
    def advance(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr(batch.time, "sleep", advance)
    batch.record_rate_result({"error": "Vertex HTTP 429"})
    assert batch.wait_for_rate_limit() is True
    assert sum(sleeps) == 60
    batch.record_rate_result({"error": "Vertex HTTP 429"})
    deadline = batch.read(tmp_path / "rate-limit.json")["resumeAfter"]
    assert deadline == 1180
    batch.record_rate_result({"nativePath": "already-in-flight.png"})
    assert batch.read(tmp_path / "rate-limit.json")["resumeAfter"] == deadline
    (tmp_path / "STOP").write_text("user pause")
    assert batch.wait_for_rate_limit() is False


def test_clothing_reference_crop_keeps_exact_pixels_and_source_binding(tmp_path):
    import pytest
    from PIL import Image
    from scripts.batch_female_nano_presets import garment_style_reference, image_ref, sha
    source = tmp_path / "source.png"
    original = Image.new("RGB", (1080, 1620), (17, 34, 51))
    original.save(source)
    ref = image_ref(source, "source")
    result = garment_style_reference(ref, [300, 640, 680, 1460], tmp_path)
    assert result["derivation"]["sourceSha256"] == sha(source)
    with Image.open(result["path"]) as cropped:
        assert cropped.tobytes() == original.crop((300, 640, 680, 1460)).tobytes()
    with pytest.raises(AssertionError):
        garment_style_reference(ref, [300, 640, 1100, 1460], tmp_path)


def test_old_failures_do_not_repeat_elapsed_backoff_and_stop_interrupts_retry(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from scripts import batch_female_nano_presets as batch
    clock = [1000.0]
    sleeps = []
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch.time, "time", lambda: clock[0])
    monkeypatch.setattr(batch.random, "random", lambda: 0)
    def advance(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr(batch.time, "sleep", advance)
    def row(at):
        return {"attempts": [{"finishedAt": datetime.fromtimestamp(at, timezone.utc).isoformat()}] * 4}
    assert batch.wait_for_retry(row(800)) is True
    assert sleeps == []
    assert batch.wait_for_retry(row(990)) is True
    assert sum(sleeps) == 50
    def pause(delay):
        advance(delay)
        (tmp_path / "STOP").write_text("user pause")
    monkeypatch.setattr(batch.time, "sleep", pause)
    assert batch.wait_for_retry(row(clock[0])) is False
    assert sum(sleeps) == 52


def test_dispatch_spacing_counts_request_time_and_429_still_takes_priority(monkeypatch, tmp_path):
    from scripts import batch_female_nano_presets as batch
    clock = [1000.0]
    sleeps = []
    monkeypatch.setattr(batch, "BATCH", tmp_path)
    monkeypatch.setattr(batch.time, "time", lambda: clock[0])
    monkeypatch.setattr(batch, "emit", lambda value: None)
    def advance(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr(batch.time, "sleep", advance)
    assert batch.wait_for_rate_limit()
    clock[0] += 20
    assert batch.wait_for_rate_limit()
    assert sum(sleeps) == 15
    batch.record_rate_result({"error": "Vertex HTTP 429"})
    assert batch.wait_for_rate_limit()
    assert sum(sleeps) == 75

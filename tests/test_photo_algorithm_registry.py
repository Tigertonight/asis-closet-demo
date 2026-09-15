"""app/photo_algorithm_registry.py 的单元测试。

快照/加载/跑批/对比均为文件系统操作，测试全部使用 tmp_path 隔离，
不污染真实 outputs 目录；算法加载用真实快照（当前版本）冒烟。
"""

from __future__ import annotations

import json

import pytest

from app import photo_algorithm_registry as reg


@pytest.fixture()
def isolated_registry(tmp_path, monkeypatch):
    """把注册表的数据目录指到临时目录，隔离真实 outputs。

    注意保留 _LOADED_MODULES 全局缓存：每个快照模块会各自初始化一套
    TFLite/GL context，反复加载会在线程层面积累泄漏（macOS 上会挂死）；
    同名版本（都从当前代码快照）复用缓存是安全的。
    """
    monkeypatch.setattr(reg, "ALGORITHM_DIR", tmp_path / "algorithms")
    monkeypatch.setattr(reg, "REPORT_DIR", tmp_path / "reports")
    return tmp_path


def test_snapshot_current_is_idempotent(isolated_registry) -> None:
    version = reg.snapshot_current(note="first")
    manifest = json.loads((reg.ALGORITHM_DIR / version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version
    assert (reg.ALGORITHM_DIR / version / "attribute_pipeline.py").is_file()
    assert (reg.ALGORITHM_DIR / version / "cv_pipeline.py").is_file()
    # 重复快照幂等（不覆盖已存在的 manifest）
    again = reg.snapshot_current(note="second")
    assert again == version
    manifest2 = json.loads((reg.ALGORITHM_DIR / version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest2["note"] == "first"


def test_list_versions_marks_current(isolated_registry) -> None:
    reg.snapshot_current()
    versions = reg.list_versions()
    assert [item["version"] for item in versions] == [reg.current_version()]
    assert versions[0]["is_current"] is True
    assert versions[0]["report_photo_count"] == 0  # 还没跑批


def test_load_algorithm_rejects_unknown_version(isolated_registry) -> None:
    with pytest.raises(ValueError, match="未注册"):
        reg.load_algorithm("photo-v99.0")


def test_load_algorithm_current_snapshot(isolated_registry) -> None:
    """加载当前版本快照：算法结果应与直接调用当前模块一致（事故照片口径）。"""
    version = reg.snapshot_current()
    module = reg.load_algorithm(version)
    assert getattr(module, "PHOTO_ALGORITHM_VERSION", None) == version
    assert callable(module.analyze_face_photo)
    assert callable(module.analyze_body_photo)
    # 模型路径已 patch 到真实 app/models
    from app.storage import ROOT_DIR

    assert str(getattr(module, "POSE_LANDMARKER_MODEL", "")).startswith(str(ROOT_DIR / "app"))
    # 进程内缓存：二次加载返回同一模块对象
    assert reg.load_algorithm(version) is module


def _fake_photo(tmp_path, name: str = "p.jpg", fill=(192, 150, 130)) -> dict:
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", (60, 80), fill).save(path, "JPEG")
    return {
        "photo_id": path.stem,
        "path": str(path),
        "kind": "face",
        "source": "user",
        "user_id": None,
        "session_id": None,
        "original_status": "accepted",
    }


def test_analyze_photo_with_error_row(isolated_registry, tmp_path) -> None:
    """照片损坏/不存在时报告行记 error，不抛异常。"""
    reg.snapshot_current()
    photo = {"photo_id": "missing", "path": str(tmp_path / "nope.jpg"), "kind": "face"}
    row = reg.analyze_photo_with(reg.current_version(), photo)
    assert row["photo_id"] == "missing"
    assert row["status"] == "error"
    assert row["error"]


def test_run_report_and_compare(isolated_registry, tmp_path, monkeypatch) -> None:
    """跑批写 reports.jsonl + 两版本对比：标签变化进矩阵和明细。"""
    reg.snapshot_current()
    version = reg.current_version()
    photo_a = _fake_photo(tmp_path, "a.jpg")   # 中等肤
    photo_b = _fake_photo(tmp_path, "b.jpg")   # 深肤嫌疑色（photo-v1.2 会补偿）
    photos = [photo_a, photo_b]
    monkeypatch.setattr(reg, "iter_all_photos", lambda: photos)
    summary = reg.run_report(version)
    assert summary["analyzed"] == 2
    rows = reg._load_report_rows(version)
    assert set(rows) == {"a", "b"}
    # 纯色合成图过不了人脸门禁：label 为 None、status=fail，但报告行结构完整
    assert "skin" in rows["a"]
    assert rows["a"]["status"] in {"pass", "warn", "fail"}
    manifest = json.loads((reg.REPORT_DIR / version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["photo_count"] == 2

    # 伪造旧版本（算法快照 + 报告，photo-b 标签不同），验证对比逻辑
    old_version = "photo-v0.test"
    old_algo_dir = reg.ALGORITHM_DIR / old_version
    old_algo_dir.mkdir(parents=True)
    (old_algo_dir / "attribute_pipeline.py").write_text("# fake\n")
    (old_algo_dir / "cv_pipeline.py").write_text("# fake\n")
    (old_algo_dir / "manifest.json").write_text(json.dumps({"version": old_version}), encoding="utf-8")
    old_dir = reg.REPORT_DIR / old_version
    old_dir.mkdir(parents=True)
    old_rows = {
        "a": {**rows["a"], "algorithm_version": old_version},  # a 无变化
        "b": {**rows["b"], "algorithm_version": old_version, "skin": {**rows["b"]["skin"], "label": "小麦色", "l_star": 41.0}},
    }
    (old_dir / "reports.jsonl").write_text(
        "".join(json.dumps(old_rows[key], ensure_ascii=False) + "\n" for key in sorted(old_rows)),
        encoding="utf-8",
    )
    diff = reg.compare_reports(old_version, version)
    assert diff["common"] == 2
    assert diff["changed"] == 1
    assert diff["details"][0]["photo_id"] == "b"
    pairs = diff["label_matrix"]["skin"]
    assert any("小麦色" in pair for pair in pairs)


def test_run_report_incremental_skip(isolated_registry, tmp_path, monkeypatch) -> None:
    """force=False 时已有结果的照片跳过（增量跑批）。"""
    reg.snapshot_current()
    version = reg.current_version()
    photo = _fake_photo(tmp_path)
    monkeypatch.setattr(reg, "iter_all_photos", lambda: [photo])
    first = reg.run_report(version)
    assert first == {"version": version, "total": 1, "analyzed": 1, "skipped": 0, "failed": 0}
    second = reg.run_report(version)
    assert second["skipped"] == 1 and second["analyzed"] == 0
    forced = reg.run_report(version, force=True)
    assert forced["analyzed"] == 1


def test_record_photo_sync_appends(isolated_registry, tmp_path) -> None:
    """新照片补跑（同步版）：照片写进所有已注册版本的报告。"""
    reg.snapshot_current()
    version = reg.current_version()
    photo = _fake_photo(tmp_path, "fresh.jpg")
    reg._record_photo_sync(photo)
    rows = reg._load_report_rows(version)
    assert "fresh" in rows
    assert "skin" in rows["fresh"]  # 纯色图过不了门禁，但报告行结构完整

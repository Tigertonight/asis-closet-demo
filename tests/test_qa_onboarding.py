"""QA 页面（/qa/onboarding-attributes）的渲染测试。

路由依赖真实模型与 qa_photos 素材，测试中 stub 掉分析层，只验证页面结构与渲染。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.qa_onboarding as qa_onboarding
from app.main import app

ADMIN_TEST_PASSWORD = "qa-admin-test-pw"


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """已登录管理后台的 client（QA 页面现在需要管理员密码）。"""

    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    client = TestClient(app)
    response = client.post("/admin/api/login", json={"password": ADMIN_TEST_PASSWORD})
    assert response.status_code == 200
    return client


def _fake_entry(kind: str = "face") -> dict:
    attribute = {
        "status": "pass",
        "label": "中性自然肤" if kind == "face" else "梨型",
        "confidence": 0.72,
        "issues": [],
        "evidence": {"l_star": 63.2, "ita_deg": 44.1} if kind == "face" else {"measurements": {"shoulder_width": 200.0, "hip_width": 240.0, "waist_width": 180.0}, "classification": {"ratios": {"hip_over_shoulder": 1.2, "waist_over_hip": 0.75}}},
    }
    attributes = {"skin_tone": attribute, "face_shape": {**attribute, "label": "椭圆脸", "candidates": [{"label": "椭圆脸", "score": 0.6}, {"label": "圆脸", "score": 0.3}]}} if kind == "face" else {"body_shape": attribute}
    return {
        "item": {"file": f"{kind}/{kind}_01.jpg", "kind": kind, "source_url": "https://example.com", "alt": "sample"},
        "result": {"status": "pass", "confidence": 0.72, "issues": [{"code": "photo.color_cast", "message": "照片整体有偏色", "suggestion": "..."}], "attributes": attributes},
    }


def test_qa_page_renders_entries(monkeypatch: pytest.MonkeyPatch, admin_client: TestClient) -> None:
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [_fake_entry("face"), _fake_entry("body")])
    client = admin_client
    response = client.get("/qa/onboarding-attributes")
    assert response.status_code == 200
    text = response.text
    assert "onboarding 属性识别 QA" in text
    assert "中性自然肤" in text and "椭圆脸" in text and "梨型" in text
    assert "photo.color_cast" in text
    assert "重新分析" in text


def test_qa_page_empty_manifest(monkeypatch: pytest.MonkeyPatch, admin_client: TestClient) -> None:
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [])
    client = admin_client
    response = client.get("/qa/onboarding-attributes")
    assert response.status_code == 200
    assert "共 0 张" in response.text


# ---------------------------------------------------------------------------
# 数据标注
# ---------------------------------------------------------------------------

MANIFEST = [
    {"file": "face/face_01.jpg", "kind": "face", "source_url": "", "alt": ""},
    {"file": "body/body_01.jpg", "kind": "body", "source_url": "", "alt": ""},
]


def _setup_annotation_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(qa_onboarding, "QA_ANNOTATIONS_PATH", tmp_path / "annotations.json")
    monkeypatch.setattr(qa_onboarding, "_load_manifest", lambda: MANIFEST)
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [_fake_entry("face"), _fake_entry("body")])
    monkeypatch.setattr(qa_onboarding, "_ensure_overlays", lambda entries, refresh=False: {})


def _create_task(client: TestClient, name: str = "第一轮标注") -> str:
    response = client.post("/qa/annotations/tasks", data={"name": name}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert "tab=annotate&task=ann_" in location
    return location.split("task=", 1)[1]


def test_create_annotation_task_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin_client: TestClient) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = admin_client
    task_id = _create_task(client)

    list_page = client.get("/qa/onboarding-attributes?tab=annotate")
    assert list_page.status_code == 200
    assert "第一轮标注" in list_page.text
    assert "详情" in list_page.text

    detail_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}")
    assert detail_page.status_code == 200
    assert "第一轮标注" in detail_page.text
    assert "保存标注" in detail_page.text
    assert "一键对比" in detail_page.text


def test_batch_save_and_clear_annotations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin_client: TestClient) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = admin_client
    task_id = _create_task(client)

    ok = client.post(
        f"/qa/annotations/{task_id}/batch",
        json={"annotations": {"face/face_01.jpg": {"skin_tone": "冷白肤", "face_shape": "椭圆脸"}, "body/body_01.jpg": {"body_shape": "梨型"}}},
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True
    stored = json.loads((tmp_path / "annotations.json").read_text(encoding="utf-8"))
    assert stored["tasks"][0]["annotations"]["face/face_01.jpg"]["face_shape"] == "椭圆脸"

    bad_value = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/face_01.jpg": {"skin_tone": "蜜糖色"}}})
    assert bad_value.status_code == 422
    bad_attr = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"body/body_01.jpg": {"skin_tone": "冷白肤"}}})
    assert bad_attr.status_code == 422
    missing_file = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/none.jpg": {"skin_tone": "冷白肤"}}})
    assert missing_file.status_code == 404

    # 整体替换语义：再次提交只含一条，其余视为清除
    cleared = client.post(f"/qa/annotations/{task_id}/batch", json={"annotations": {"face/face_01.jpg": {"skin_tone": "暖白肤"}}})
    assert cleared.status_code == 200
    stored = json.loads((tmp_path / "annotations.json").read_text(encoding="utf-8"))
    assert stored["tasks"][0]["annotations"] == {"face/face_01.jpg": {"skin_tone": "暖白肤"}}


def test_diff_filter_shows_only_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin_client: TestClient) -> None:
    _setup_annotation_env(monkeypatch, tmp_path)
    client = admin_client
    task_id = _create_task(client)

    # face_01 算法识别为 中性自然肤/椭圆脸：标对一个、标错一个；body_01 标对
    client.post(
        f"/qa/annotations/{task_id}/batch",
        json={"annotations": {"face/face_01.jpg": {"skin_tone": "中性自然肤", "face_shape": "方脸"}, "body/body_01.jpg": {"body_shape": "梨型"}}},
    )

    all_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}")
    assert "不一致 1" in all_page.text
    assert "算法：椭圆脸 ≠ 标注：方脸" in all_page.text

    diff_page = client.get(f"/qa/onboarding-attributes?tab=annotate&task={task_id}&diff=1")
    assert "face/face_01.jpg" in diff_page.text
    assert "body/body_01.jpg" not in diff_page.text


# ---------------------------------------------------------------------------
# 数据分布与上传
# ---------------------------------------------------------------------------

def test_dataset_tab_renders_distribution(monkeypatch: pytest.MonkeyPatch, admin_client: TestClient) -> None:
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: [_fake_entry("face"), _fake_entry("body")])
    monkeypatch.setattr(qa_onboarding, "_ensure_overlays", lambda entries, refresh=False: {})
    monkeypatch.setattr(qa_onboarding, "QA_ANNOTATIONS_PATH", Path("/tmp/nonexistent_annotations.json"))
    client = admin_client
    response = client.get("/qa/onboarding-attributes?tab=dataset")
    assert response.status_code == 200
    text = response.text
    assert "数据分布" in text
    assert "肤色" in text and "脸型" in text and "身型" in text
    assert "最紧缺" in text
    assert "/qa/photos/upload" in text
    assert "中性自然肤" in text and "梨型" in text


def test_upload_photo_adds_to_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin_client: TestClient) -> None:
    photo_dir = tmp_path / "qa_photos"
    (photo_dir / "face").mkdir(parents=True)
    monkeypatch.setattr(qa_onboarding, "QA_PHOTO_DIR", photo_dir)
    monkeypatch.setattr(qa_onboarding, "QA_RESULTS_CACHE", photo_dir / "_results.json")
    client = admin_client

    import io as _io

    from PIL import Image as _Image

    buffer = _io.BytesIO()
    _Image.new("RGB", (600, 800), (200, 180, 170)).save(buffer, "JPEG")
    response = client.post(
        "/qa/photos/upload",
        data={"kind": "face"},
        files={"image": ("test.jpg", buffer.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "uploaded=" in response.headers["location"]

    manifest = json.loads((photo_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["kind"] == "face"
    assert manifest[0]["file"].startswith("face/upload_face_")
    assert (photo_dir / manifest[0]["file"]).exists()
    cache = json.loads((photo_dir / "_results.json").read_text(encoding="utf-8"))
    assert manifest[0]["file"] in cache  # 上传时已跑过算法

    # 重复上传同一内容 → 去重跳过
    dup = client.post(
        "/qa/photos/upload",
        data={"kind": "face"},
        files={"image": ("test.jpg", buffer.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )
    assert "upload_dup=" in dup.headers["location"]
    manifest = json.loads((photo_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1



def test_qa_page_redirects_anonymous_to_admin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """QA 实验数据页未登录 → 307 跳转管理后台；错误密码 → 401。"""

    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    anonymous = TestClient(app)

    page = anonymous.get("/qa/onboarding-attributes", follow_redirects=False)
    upload = anonymous.post(
        "/qa/photos/upload",
        data={"kind": "face"},
        files={"image": ("t.jpg", b"fake", "image/jpeg")},
        follow_redirects=False,
    )
    bad_login = anonymous.post("/admin/api/login", json={"password": "wrong-password"})
    ok_login = anonymous.post("/admin/api/login", json={"password": ADMIN_TEST_PASSWORD})

    assert page.status_code == 307
    assert page.headers["location"] == "/admin"
    assert upload.status_code == 307
    assert bad_login.status_code == 401
    assert ok_login.status_code == 200
    # 登录后（cookie 生效）可访问
    assert anonymous.get("/qa/onboarding-attributes").status_code == 200


def test_admin_password_change_revokes_sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """后台改密码：旧密码失效、旧 session 被吊销、新密码可登录。"""

    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    client = TestClient(app)
    assert client.post("/admin/api/login", json={"password": ADMIN_TEST_PASSWORD}).status_code == 200

    changed = client.put(
        "/admin/api/password",
        json={"current_password": ADMIN_TEST_PASSWORD, "new_password": "new-pw-456789"},
    )
    old_session = client.get("/admin/api/analytics/summary")

    assert changed.status_code == 200
    # 改密码后旧 session 已被吊销
    assert old_session.status_code == 401
    # 旧密码不能再登录，新密码可以
    assert client.post("/admin/api/login", json={"password": ADMIN_TEST_PASSWORD}).status_code == 401
    assert client.post("/admin/api/login", json={"password": "new-pw-456789"}).status_code == 200


def test_admin_api_rejects_phone_user_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """手机号登录用户的 token 无管理权限（403）。"""

    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "auth" / "auth_store.json")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    client = TestClient(app)
    login = client.post("/auth/phone/direct", json={"phone": "13800000001"})

    response = client.get(
        "/admin/api/analytics/summary",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert login.status_code == 200
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 照片来源体系：builtin / admin / mirror / app 四类 + 归档 + 筛选
# ---------------------------------------------------------------------------

def test_entry_source_infers_legacy_entries() -> None:
    """旧 manifest 条目没有 source 字段：按采集标记推断，新数据直接读。"""

    assert qa_onboarding.entry_source({"file": "face/face_01.jpg", "author": "a photographer", "query": "smile"}) == "builtin"
    assert qa_onboarding.entry_source({"file": "face/face_01.jpg", "author": "同事上传", "query": "手动上传"}) == "admin"
    assert qa_onboarding.entry_source({"file": "face/user_face_x.jpg", "source": "app"}) == "app"
    assert qa_onboarding.entry_source({"file": "face/user_face_x.jpg", "source": "mirror"}) == "mirror"
    assert qa_onboarding.entry_source({"file": "face/x.jpg", "source": "admin"}) == "admin"
    assert qa_onboarding.entry_source({"file": "face/x.jpg", "source": "builtin"}) == "builtin"


def test_archive_user_photo_marks_source_and_dedupes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """用户照片归档进 QA 数据集：写 source、缩图、内容 hash 去重；重复归档静默跳过。"""

    import io as _io

    from PIL import Image as _Image

    photo_dir = tmp_path / "qa_photos"
    monkeypatch.setattr(qa_onboarding, "QA_PHOTO_DIR", photo_dir)
    monkeypatch.setattr(qa_onboarding, "QA_RESULTS_CACHE", photo_dir / "_results.json")

    image = _Image.new("RGB", (2400, 3000), (200, 180, 170))
    assert qa_onboarding.archive_user_photo(image, "face", "app") is True
    manifest = json.loads((photo_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["source"] == "app"
    assert manifest[0]["file"].startswith("face/user_face_")
    # 长边压到 1600
    with _Image.open(photo_dir / manifest[0]["file"]) as stored:
        assert max(stored.size) <= 1600

    # 同内容重复归档 → 跳过
    assert qa_onboarding.archive_user_photo(image, "face", "app") is False
    manifest = json.loads((photo_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1

    # 非用户来源不归档
    assert qa_onboarding.archive_user_photo(image, "face", "builtin") is False


def test_upload_photo_marks_admin_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin_client: TestClient) -> None:
    """管理员上传的照片进 manifest 时标记 source=admin。"""

    photo_dir = tmp_path / "qa_photos"
    (photo_dir / "face").mkdir(parents=True)
    monkeypatch.setattr(qa_onboarding, "QA_PHOTO_DIR", photo_dir)
    monkeypatch.setattr(qa_onboarding, "QA_RESULTS_CACHE", photo_dir / "_results.json")

    import io as _io

    from PIL import Image as _Image

    buffer = _io.BytesIO()
    _Image.new("RGB", (600, 800), (200, 180, 170)).save(buffer, "JPEG")
    response = admin_client.post(
        "/qa/photos/upload",
        data={"kind": "face"},
        files={"image": ("admin.jpg", buffer.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    manifest = json.loads((photo_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["source"] == "admin"


def _entry_with_source(kind: str, source: str) -> dict:
    entry = _fake_entry(kind)
    entry["item"] = {
        **entry["item"],
        "source": source,
        "file": f"{kind}/photo_{source}_{kind}.jpg",
    }
    return entry


def test_qa_page_source_filter(monkeypatch: pytest.MonkeyPatch, admin_client: TestClient) -> None:
    """来源筛选：默认全部显示；指定来源只显示对应条目，筛选条带计数。"""

    entries = [
        _entry_with_source("face", "builtin"),
        _entry_with_source("face", "mirror"),
        _entry_with_source("body", "app"),
    ]
    monkeypatch.setattr(qa_onboarding, "_analyze_all", lambda refresh=False: entries)
    monkeypatch.setattr(qa_onboarding, "_ensure_overlays", lambda entries, refresh=False: {})

    all_view = admin_client.get("/qa/onboarding-attributes").text
    assert "全部" in all_view and "内置" in all_view and "镜子拍照" in all_view and "App 拍照" in all_view and "管理员上传" in all_view
    assert "photo_builtin_face.jpg" in all_view

    mirror_view = admin_client.get("/qa/onboarding-attributes?source=mirror").text
    assert "src-badge--mirror" in mirror_view
    assert "photo_builtin_face.jpg" not in mirror_view  # builtin 条目被过滤
    assert "photo_app_body.jpg" not in mirror_view  # app 条目被过滤
    # 筛选状态保持：重新分析链接带 source
    assert "source=mirror" in mirror_view

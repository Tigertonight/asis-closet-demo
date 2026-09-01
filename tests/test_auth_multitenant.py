from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth
import app.main as main_module
import app.storage as storage
from app.main import app


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image(color: tuple[int, int, int] = (220, 60, 105)) -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = color
    return image


def _use_tmp_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")


def _login(client: TestClient, phone: str) -> dict[str, str]:
    start = client.post("/auth/phone/start", json={"phone": phone}).json()
    verified = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()
    return {"Authorization": f"Bearer {verified['access_token']}"}


def test_phone_login_creates_and_reuses_user(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    first = client.post("/auth/phone/start", json={"phone": "13800000001"}).json()
    verified = client.post("/auth/phone/verify", json={"phone": "13800000001", "code": first["dev_code"]}).json()
    second = client.post("/auth/phone/start", json={"phone": "13800000001"}).json()
    verified_again = client.post("/auth/phone/verify", json={"phone": "13800000001", "code": second["dev_code"]}).json()

    assert verified["status"] == "ok"
    assert verified["user"]["phone_e164"] == "+8613800000001"
    assert verified_again["user"]["user_id"] == verified["user"]["user_id"]
    assert "dev_code" not in auth.AUTH_STORE_PATH.read_text(encoding="utf-8")


def test_phone_code_rejects_wrong_and_reused_code(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    start = client.post("/auth/phone/start", json={"phone": "13800000002"}).json()
    wrong = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": "000000"})
    ok = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": start["dev_code"]})
    reused = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": start["dev_code"]})

    assert wrong.status_code == 400
    assert ok.status_code == 200
    assert reused.status_code == 400


def test_public_demo_does_not_return_dev_code(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_ENV", "demo")
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "test-public-secret-that-is-not-default")
    monkeypatch.delenv("SELFIT_AUTH_RETURN_DEV_CODE", raising=False)
    client = TestClient(app)

    start = client.post("/auth/phone/start", json={"phone": "13800000021"}).json()

    assert start["status"] == "sent"
    assert "dev_code" not in start


def test_public_demo_rejects_default_auth_secret(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_ENV", "demo")
    monkeypatch.delenv("SELFIT_AUTH_SECRET", raising=False)
    client = TestClient(app)

    response = client.post("/auth/phone/start", json={"phone": "13800000022"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "auth.http_500"


def test_auth_rate_limit_is_enforced(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("SELFIT_PHONE_LOGIN_RATE_LIMIT", "1")
    monkeypatch.setenv("SELFIT_PHONE_LOGIN_RATE_WINDOW_SECONDS", "3600")
    client = TestClient(app)
    headers = {"x-forwarded-for": "203.0.113.77"}

    first = client.post("/auth/phone/start", json={"phone": "13800000023"}, headers=headers)
    second = client.post("/auth/phone/start", json={"phone": "13800000024"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "request.rate_limited"


def test_phone_direct_login_creates_phone_unique_account(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    ip_headers = {"x-real-ip": "198.51.100.10"}

    first = client.post("/auth/phone/direct", json={"phone": "13800000011"}, headers=ip_headers)
    # 换 IP 再登录同一手机号 → 仍是同一账号（手机号唯一，不绑 IP）
    second = client.post(
        "/auth/phone/direct",
        json={"phone": "13800000011"},
        headers={"x-real-ip": "203.0.113.99"},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert first.json()["user"]["phone_e164"] == "+8613800000011"
    assert second.json()["user"]["user_id"] == first.json()["user"]["user_id"]
    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    record = next(user for user in store["users"] if user["user_id"] == first.json()["user"]["user_id"])
    assert record["auth_provider"] == "phone_direct"
    assert record["phone_e164"] == "+8613800000011"
    # 无 PIN 方案：不存储任何 PIN 凭证
    assert "pin_hash" not in record


def test_phone_direct_login_rejects_unallocated_segments(monkeypatch, tmp_path: Path) -> None:
    """10x/12x 等未启用号段应被拒绝，只有 1[3-9] 开头是有效大陆手机号。"""

    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    invalid = client.post("/auth/phone/direct", json={"phone": "12000000000"})
    short = client.post("/auth/phone/direct", json={"phone": "1380000001"})

    assert invalid.status_code == 400
    assert short.status_code == 400
    # 拒绝的请求不应产生任何账号副作用
    store_path = auth.AUTH_STORE_PATH
    assert not store_path.exists() or json.loads(store_path.read_text(encoding="utf-8"))["users"] == []


def test_phone_direct_login_reuses_legacy_phone_account(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    started = client.post("/auth/phone/start", json={"phone": "13800000013"}).json()
    verified = client.post(
        "/auth/phone/verify", json={"phone": "13800000013", "code": started["dev_code"]}
    ).json()

    # 老的手机号账号（短信验证码登录创建）direct 登录直接复用
    direct = client.post(
        "/auth/phone/direct",
        json={"phone": "13800000013"},
        headers={"x-real-ip": "198.51.100.99"},
    )

    assert direct.status_code == 200
    assert direct.json()["user"]["user_id"] == verified["user"]["user_id"]


def test_phone_direct_login_can_be_disabled(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_AUTH_ALLOW_PHONE_DIRECT", "0")
    client = TestClient(app)

    response = client.post("/auth/phone/direct", json={"phone": "13800000015"})

    assert response.status_code == 503


def test_invite_login_stays_ip_bound_for_internal_use(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "ROADSHOW-2026")
    client = TestClient(app)
    ip_headers = {"x-real-ip": "198.51.100.20"}

    invited = client.post("/auth/invite/verify", json={"invite_code": "ROADSHOW-2026"}, headers=ip_headers)
    direct = client.post(
        "/auth/phone/direct",
        json={"phone": "13800000016"},
        headers=ip_headers,
    )

    # 邀请码登录保留 IP 绑定（内部测试）；手机号登录走独立账号
    assert invited.status_code == 200
    assert direct.status_code == 200
    assert direct.json()["user"]["user_id"] != invited.json()["user"]["user_id"]


def test_xhs_image_proxy_uses_disk_cache(monkeypatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "xhs_images"
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(main_module, "XHS_IMAGE_CACHE_DIR", cache_dir)
    source_url = "https://sns-webpic-qc.xhscdn.com/path/to/cover!nc_n_webp_mw_1"
    image_bytes = _png_bytes(Image.new("RGB", (12, 12), "#ff4f86"))

    written = main_module._write_xhs_image_cache(source_url, image_bytes, "image/png")
    cached = main_module._cached_xhs_image_response(source_url)

    assert written.status_code == 200
    assert cached is not None
    assert cached.status_code == 200
    assert any(path.suffix == ".png" for path in cache_dir.iterdir())
    assert any(path.suffix == ".json" for path in cache_dir.iterdir())


def test_closet_requires_login_and_isolates_user_data(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    user_a = _login(client, "13800000003")
    user_b = _login(client, "13800000004")

    anonymous = client.get("/closet/items")
    created = client.post(
        "/closet/import/upload",
        headers=user_a,
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    a_items = client.get("/closet/items", headers=user_a).json()
    b_items = client.get("/closet/items", headers=user_b).json()
    b_detail = client.get(f"/closet/items/{created['item_id']}", headers=user_b)

    assert anonymous.status_code == 401
    assert a_items["total"] == 1
    assert b_items["total"] == 0
    assert b_detail.status_code == 404
    assert created["user_id"] != "local_user"
    assert (tmp_path / "outputs" / "users" / created["user_id"] / "closet" / "closet_manifest.json").exists()


def test_user_assets_are_read_under_current_user_only(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    user_a = _login(client, "13800000005")
    user_b = _login(client, "13800000006")

    created = client.post(
        "/closet/import/upload",
        headers=user_a,
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image((60, 120, 220))), "image/png"))],
    ).json()["items"][0]
    asset_path = created["assets"]["preview_path"]

    assert client.get(asset_path, headers=user_a).status_code == 200
    assert client.get(asset_path, headers=user_b).status_code == 404


def test_missing_demo_asset_is_backfilled_for_existing_user(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = _login(client, "13800000007")
    user_id = client.get("/auth/me", headers=headers).json()["user"]["user_id"]

    demo_asset = storage.storage_context(storage.LOCAL_USER_ID).closet_output_dir / "items" / "demo_top" / "cutout.png"
    demo_asset.parent.mkdir(parents=True, exist_ok=True)
    demo_asset.write_bytes(_png_bytes(_synthetic_top_image((180, 80, 120))))

    user_asset_dir = storage.storage_context(user_id).closet_output_dir / "items" / "demo_top"
    user_asset_dir.mkdir(parents=True, exist_ok=True)
    assert not (user_asset_dir / "cutout.png").exists()

    response = client.get("/user-assets/closet/items/demo_top/cutout.png", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert (user_asset_dir / "cutout.png").exists()


def test_phone_direct_login_not_throttled_by_admin_auth_rule(monkeypatch, tmp_path: Path) -> None:
    """路演场景：商场 WiFi 下大量用户共享出口 IP。

    手机号直接登录（无资产可盗）与 admin 登录（防密码枚举）限流规则分离：
    auth 限到 1 次/小时时，手机号登录不受影响，admin 登录立即被限。
    """

    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("SELFIT_AUTH_RATE_LIMIT", "1")
    monkeypatch.setenv("SELFIT_AUTH_RATE_WINDOW_SECONDS", "3600")
    monkeypatch.setenv("SELFIT_PHONE_LOGIN_RATE_LIMIT", "600")
    client = TestClient(app)
    headers = {"x-forwarded-for": "203.0.113.99"}

    # 手机号登录：auth=1 也不受影响（独立 phone_login 规则）
    for i in range(3):
        response = client.post("/auth/phone/direct", json={"phone": f"1380000030{i}"}, headers=headers)
        assert response.status_code == 200, f"第 {i + 1} 次手机号登录不应被限流"

    # admin 登录：auth 规则独立计数（第一次放行进入密码校验，第二次即被限）
    first_admin = client.post("/admin/api/login", json={"password": "whatever"}, headers=headers)
    assert first_admin.status_code == 401  # 密码错误（auth 规则的首次配额未被 phone 登录消耗）
    second_admin = client.post("/admin/api/login", json={"password": "whatever"}, headers=headers)
    assert second_admin.status_code == 429
    assert second_admin.json()["error"]["code"] == "request.rate_limited"

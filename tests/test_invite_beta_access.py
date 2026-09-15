"""内测邀请码席位制 / beta 门槛 / 试穿日额度 / 手机号绑定合并 的行为测试。"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import app.auth as auth
import app.beta_access as beta_access
import app.storage as storage
from app.main import app


def _use_tmp_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")


def _invite_login(client: TestClient, code: str, device_id: str, ip: str = "198.51.100.10") -> dict:
    response = client.post(
        "/auth/invite/verify",
        json={"invite_code": code, "device_id": device_id},
        headers={"x-real-ip": ip},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _phone_login(client: TestClient, phone: str) -> dict:
    response = client.post("/auth/phone/direct", json={"phone": phone})
    assert response.status_code == 200, response.text
    return response.json()


def _bearer(payload: dict) -> dict:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_invite_seats_limit_rejects_new_devices(monkeypatch, tmp_path: Path) -> None:
    """席位制：同一设备重登不占席位；席满后新设备被 410 拒绝。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-01")
    monkeypatch.setenv("SELFIT_INVITE_MAX_SEATS", "3")
    client = TestClient(app)

    first = _invite_login(client, "PILOT-01", "device-0001")
    for index in range(2, 4):
        _invite_login(client, "PILOT-01", f"device-000{index}")

    # 同一设备重登：不消耗席位，还是原账号。
    again = _invite_login(client, "PILOT-01", "device-0001")
    assert again["user"]["user_id"] == first["user"]["user_id"]

    # 第 4 个新设备：席满拒绝，文案指向"换一个码"。
    rejected = client.post(
        "/auth/invite/verify",
        json={"invite_code": "PILOT-01", "device_id": "device-0004"},
        headers={"x-real-ip": "198.51.100.10"},
    )
    assert rejected.status_code == 410
    assert "名额已用尽" in rejected.json()["detail"]


def test_invite_code_expiry_blocks_new_users_but_not_existing(monkeypatch, tmp_path: Path) -> None:
    """码过期：拒绝新用户，已绑定老用户仍可静默重登。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-EXPIRE")
    client = TestClient(app)

    early = _invite_login(client, "PILOT-EXPIRE", "device-early-01")
    data = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    for record in data["invite_codes"]:
        record["expires_at"] = "2000-01-01T00:00:00+00:00"
    auth.AUTH_STORE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    late = client.post(
        "/auth/invite/verify",
        json={"invite_code": "PILOT-EXPIRE", "device_id": "device-late-99"},
        headers={"x-real-ip": "198.51.100.10"},
    )
    assert late.status_code == 410

    returning = _invite_login(client, "PILOT-EXPIRE", "device-early-01")
    assert returning["user"]["user_id"] == early["user"]["user_id"]


def test_invite_token_cannot_access_admin_api(monkeypatch, tmp_path: Path) -> None:
    """安全修复：邀请码是发给外部评委的共享凭证，不能进管理后台。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-ADMIN")
    client = TestClient(app)

    invited = _invite_login(client, "PILOT-ADMIN", "device-admin-01")
    response = client.get("/admin/api/analytics/summary", headers=_bearer(invited))
    assert response.status_code == 403


def test_beta_gate_blocks_tryon_and_stylist_for_normal_users(monkeypatch, tmp_path: Path) -> None:
    """普通手机号用户（无邀请码）被挡在消耗 token 的主站行为之外。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    normal = _phone_login(client, "13800000001")
    stylist = client.post(
        "/stylist/chat",
        json={"message": "今天穿什么"},
        headers=_bearer(normal),
    )
    assert stylist.status_code == 403
    assert "邀请码" in stylist.json()["detail"]

    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "#ffffff").save(buffer, "PNG")
    buffer.seek(0)
    tryon = client.post(
        "/selfit/try-on/jobs",
        files={"person_image": ("p.png", buffer, "image/png")},
        data={"outfit_id": "whatever"},
        headers=_bearer(normal),
    )
    assert tryon.status_code == 403
    assert tryon.headers['X-Selfit-Access'] == 'invite-required'
    assert tryon.json()['error']['code'] == 'auth.invite_required'


@pytest.mark.parametrize(('mode', 'public', 'enabled', 'allowed'), [
    ('local', '0', None, False),
    ('local', '0', '0', False),
    ('local', '0', '1', True),
    ('local', '1', '1', False),
    ('production', '0', '1', False),
    ('prod', '0', '1', False),
    ('demo', '0', '1', False),
    ('staging', '0', '1', False),
    ('test', '0', '1', False),
])
def test_local_invite_free_access_is_explicit_and_never_persisted(
    monkeypatch, tmp_path, mode, public, enabled, allowed,
) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv('SELFIT_ENV', mode)
    monkeypatch.setenv('SELFIT_AUTH_SECRET', 'test-only-invite-boundary-secret')
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', public)
    if enabled is not None:
        monkeypatch.setenv('SELFIT_LOCAL_BETA_ACCESS', enabled)
    client = TestClient(app)
    guest = client.post('/auth/guest').json()
    assert guest['user']['beta_qualified'] is allowed
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials=guest['access_token'])
    if allowed:
        user = asyncio.run(beta_access.require_beta_tryon(credentials))
        assert user['user_id'] == guest['user']['user_id']
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(beta_access.require_beta_tryon(credentials))
        assert error.value.status_code == 403
        assert error.value.headers['X-Selfit-Access'] == 'invite-required'
    data = json.loads(auth.AUTH_STORE_PATH.read_text())
    raw_user = next(user for user in data['users'] if user['user_id'] == guest['user']['user_id'])
    assert not raw_user.get('beta_qualified'), 'local access must not permanently qualify the account'
    assert not raw_user.get('invite_code_id')
    monkeypatch.setenv('SELFIT_ENV', 'production')
    assert client.get('/auth/me', headers=_bearer(guest)).json()['user']['beta_qualified'] is False


def test_guest_unlock_keeps_same_account_and_session(monkeypatch, tmp_path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv('SELFIT_INVITE_CODES', 'GUEST-UPGRADE')
    client = TestClient(app)
    guest = client.post('/auth/guest').json()
    headers = _bearer(guest)
    invalid = client.post('/auth/invite/upgrade', json={'invite_code': 'WRONG'}, headers=headers)
    assert invalid.status_code == 400
    assert client.get('/auth/me', headers=headers).json()['user']['beta_qualified'] is False
    upgraded = client.post('/auth/invite/upgrade', json={
        'invite_code': 'GUEST-UPGRADE', 'device_id': 'guest-test-device',
    }, headers=headers)
    assert upgraded.status_code == 200
    assert upgraded.json()['user']['user_id'] == guest['user']['user_id']
    assert client.get('/auth/me', headers=headers).json()['user']['beta_qualified'] is True


def test_local_access_still_requires_auth_and_respects_quota(monkeypatch, tmp_path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv('SELFIT_ENV', 'local')
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', '0')
    monkeypatch.setenv('SELFIT_LOCAL_BETA_ACCESS', '1')
    monkeypatch.setenv('SELFIT_TRYON_DAILY_LIMIT', '1')
    with pytest.raises(HTTPException) as error:
        asyncio.run(beta_access.require_beta_user(None))
    assert error.value.status_code == 401
    guest = TestClient(app).post('/auth/guest').json()
    beta_access.consume_tryon_quota(guest['user']['user_id'])
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials=guest['access_token'])
    with pytest.raises(HTTPException) as error:
        asyncio.run(beta_access.require_beta_tryon(credentials))
    assert error.value.status_code == 429


def test_tryon_daily_quota_enforced_and_resets_next_day(monkeypatch, tmp_path: Path) -> None:
    """30 次/天：超额 429，次日（北京时间）刷新。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_TRYON_DAILY_LIMIT", "3")
    user_id = "u_quota_test"

    for _ in range(3):
        beta_access.consume_tryon_quota(user_id)
    exhausted = None
    try:
        beta_access.consume_tryon_quota(user_id)
    except Exception as error:  # fastapi HTTPException
        exhausted = error

    assert exhausted is not None
    assert getattr(exhausted, "status_code", None) == 429
    assert "额度已用完" in str(exhausted.detail)
    assert beta_access.tryon_remaining_today(user_id) == 0

    # 直接改写用量文件模拟次日：配额恢复。
    usage_path = tmp_path / "outputs" / "auth" / "quota_usage.json"
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    day_key = next(iter(usage[user_id]))
    usage[user_id] = {f"{day_key}x-tomorrow": 3}
    usage_path.write_text(json.dumps(usage), encoding="utf-8")
    assert beta_access.tryon_remaining_today(user_id) == 3


def test_bind_phone_without_existing_account_attaches_in_place(monkeypatch, tmp_path: Path) -> None:
    """场景 A：邀请码账号绑手机号（无冲突）——同账号挂上手机号，beta 资格保留。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-BIND")
    client = TestClient(app)

    invited = _invite_login(client, "PILOT-BIND", "device-bind-01")
    bound = client.post(
        "/auth/bind-phone",
        json={"phone": "13900000001", "device_id": "device-bind-01"},
        headers=_bearer(invited),
    )
    assert bound.status_code == 200
    assert bound.json()["merged"] is False
    assert bound.json()["user"]["phone_e164"] == "+8613900000001"
    assert bound.json()["user"]["beta_qualified"] is True

    # 手机号登录落到同一账号。
    phone_login = _phone_login(client, "13900000001")
    assert phone_login["user"]["user_id"] == invited["user"]["user_id"]


def test_bind_phone_merges_existing_phone_account_data(monkeypatch, tmp_path: Path) -> None:
    """场景 B：手机号已有账号——双边数据合并，当前（邀请码）账号为幸存身份。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-MERGE")
    client = TestClient(app)

    # 先给手机号账号造点数据：写一份衣橱清单。
    phone_user = _phone_login(client, "13900000002")
    phone_user_id = phone_user["user"]["user_id"]
    closet_dir = tmp_path / "outputs" / "users" / phone_user_id / "closet"
    closet_dir.mkdir(parents=True, exist_ok=True)
    (closet_dir / "closet_manifest.json").write_text(
        json.dumps({"version": 1, "items": [
            {"item_id": "item_phone_1", "user_id": phone_user_id, "title": "手机号账号的单品", "updated_at": "2026-09-01T00:00:00+00:00"},
            {"item_id": "item_shared", "user_id": phone_user_id, "title": "旧版本", "updated_at": "2026-09-01T00:00:00+00:00"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )

    invited = _invite_login(client, "PILOT-MERGE", "device-merge-01")
    invited_user_id = invited["user"]["user_id"]
    invited_closet = tmp_path / "outputs" / "users" / invited_user_id / "closet"
    invited_closet.mkdir(parents=True, exist_ok=True)
    (invited_closet / "closet_manifest.json").write_text(
        json.dumps({"version": 1, "items": [
            {"item_id": "item_invite_1", "user_id": invited_user_id, "title": "邀请码账号的单品", "updated_at": "2026-09-02T00:00:00+00:00"},
            {"item_id": "item_shared", "user_id": invited_user_id, "title": "新版本", "updated_at": "2026-09-03T00:00:00+00:00"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )

    bound = client.post(
        "/auth/bind-phone",
        json={"phone": "13900000002", "device_id": "device-merge-01"},
        headers=_bearer(invited),
    )
    assert bound.status_code == 200
    assert bound.json()["merged"] is True

    # 合并后：幸存账号清单包含两边条目，同 id 冲突取 updated_at 新者，user_id 归属幸存账号。
    merged_manifest = json.loads((invited_closet / "closet_manifest.json").read_text(encoding="utf-8"))
    items = {item["item_id"]: item for item in merged_manifest["items"]}
    assert {"item_phone_1", "item_invite_1", "item_shared"} <= set(items)
    assert items["item_shared"]["title"] == "新版本"
    assert all(item["user_id"] == invited_user_id for item in merged_manifest["items"])

    # 手机号随后登录落到幸存账号；旧账号标记 merged。
    phone_login = _phone_login(client, "13900000002")
    assert phone_login["user"]["user_id"] == invited_user_id
    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    merged_user = next(user for user in store["users"] if user["user_id"] == phone_user_id)
    assert merged_user["status"] == "merged"
    assert merged_user["merged_into"] == invited_user_id


def test_phone_user_upgrades_with_invite_keeps_data(monkeypatch, tmp_path: Path) -> None:
    """场景 C：普通手机号用户输码解锁——原地升级，数据不迁移，占 1 席位。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-UPGRADE")
    monkeypatch.setenv("SELFIT_INVITE_MAX_SEATS", "1")
    client = TestClient(app)

    normal = _phone_login(client, "13800000003")
    assert normal["user"]["beta_qualified"] is False

    upgraded = client.post(
        "/auth/invite/upgrade",
        json={"invite_code": "PILOT-UPGRADE", "device_id": "device-upg-01"},
        headers=_bearer(normal),
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["user"]["beta_qualified"] is True
    assert upgraded.json()["user"]["user_id"] == normal["user"]["user_id"]

    # 幂等：重复升级不占新席位。
    again = client.post(
        "/auth/invite/upgrade",
        json={"invite_code": "PILOT-UPGRADE", "device_id": "device-upg-01"},
        headers=_bearer(normal),
    )
    assert again.status_code == 200

    # 席位已被场景 C 占满：新设备被拒。
    rejected = client.post(
        "/auth/invite/verify",
        json={"invite_code": "PILOT-UPGRADE", "device_id": "device-upg-02"},
        headers={"x-real-ip": "198.51.100.10"},
    )
    assert rejected.status_code == 410


def test_phone_bound_invite_is_lifetime_across_all_relogin_paths(monkeypatch, tmp_path: Path) -> None:
    """终身绑定回归：手机号输过一次邀请码后，任何重登路径都不再需要邀请码。

    规则：邀请码一旦输入就终身绑定这个手机号——之后码过期、席位用尽，
    同设备重登 / 换设备 / 短信验证码 / 设备静默续登全部保留内测资格，
    消耗型端点不再出现 invite-required 门槛；再出现输入邀请码的位置即 bug。
    """
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "LIFETIME-01")
    monkeypatch.setenv("SELFIT_INVITE_MAX_SEATS", "1")
    client = TestClient(app)

    # 唯一一次输入邀请码：普通手机号账号在解锁页升级（占满唯一席位）。
    normal = _phone_login(client, "13800000111")
    assert normal["user"]["beta_qualified"] is False
    upgraded = client.post(
        "/auth/invite/upgrade",
        json={"invite_code": "LIFETIME-01", "device_id": "device-life-01"},
        headers=_bearer(normal),
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["user"]["beta_qualified"] is True

    # 之后运营侧把码过期并停用：新设备再也进不来（席位视角这个手机号是唯一持有者）。
    data = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    for record in data["invite_codes"]:
        record["expires_at"] = "2000-01-01T00:00:00+00:00"
        record["status"] = "disabled"
    auth.AUTH_STORE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    rejected = client.post(
        "/auth/invite/verify",
        json={"invite_code": "LIFETIME-01", "device_id": "device-stranger-01"},
        headers={"x-real-ip": "198.51.100.10"},
    )
    assert rejected.status_code == 410

    # 但已绑定手机号的所有重登路径都保留内测资格，不依赖邀请码状态。
    same_device = _phone_login(client, "13800000111")
    assert same_device["user"]["beta_qualified"] is True
    assert same_device["user"]["user_id"] == normal["user"]["user_id"]

    new_device = client.post(
        "/auth/phone/direct", json={"phone": "13800000111", "device_id": "device-life-02"}
    ).json()
    assert new_device["user"]["beta_qualified"] is True
    assert new_device["user"]["user_id"] == normal["user"]["user_id"]

    started = client.post("/auth/phone/start", json={"phone": "13800000111"}).json()
    verified = client.post(
        "/auth/phone/verify", json={"phone": "13800000111", "code": started["dev_code"]}
    ).json()
    assert verified["user"]["beta_qualified"] is True

    resumed = client.post("/auth/phone/resume", json={"device_id": "device-life-02"}).json()
    assert resumed["user"]["beta_qualified"] is True

    # 消耗型端点不再出现邀请码门槛。
    stylist = client.post(
        "/stylist/chat",
        json={"message": "今天穿什么"},
        headers=_bearer(verified),
    )
    assert stylist.status_code != 403

    # 兜底幂等：已内测账号即使再次提交解锁请求（前端 bug 才会出现），也不校验码、不占席位。
    again = client.post(
        "/auth/invite/upgrade",
        json={"invite_code": "WRONG-CODE"},
        headers=_bearer(verified),
    )
    assert again.status_code == 200
    assert client.get("/auth/me", headers=_bearer(verified)).json()["user"]["beta_qualified"] is True


def test_sliding_session_renewal_for_beta_users(monkeypatch, tmp_path: Path) -> None:
    """滑动续期：剩余不到一半 TTL 时自动顺延；内测账号不掉登录态。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-SLIDE")
    client = TestClient(app)

    invited = _invite_login(client, "PILOT-SLIDE", "device-slide-01")
    headers = _bearer(invited)

    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    session = next(item for item in store["auth_sessions"] if item["user_id"] == invited["user"]["user_id"])
    assert session["sliding"] is True
    original_expiry = session["expires_at"]

    # 把过期时间改到 8 天后（< 15 天阈值），任意请求触发顺延。
    from datetime import datetime, timedelta, timezone

    session["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
    auth.AUTH_STORE_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["quota"]["tryon_daily_limit"] == 30

    renewed = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    renewed_session = next(item for item in renewed["auth_sessions"] if item["user_id"] == invited["user"]["user_id"])
    assert renewed_session["expires_at"] > original_expiry


def test_admin_invite_management_endpoints(monkeypatch, tmp_path: Path) -> None:
    """后台邀请码管理：新建 / 调席位 / 停启用 / 列表用量。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "admin-pass-123")
    client = TestClient(app)

    login = client.post("/admin/api/login", json={"password": "admin-pass-123"}).json()
    admin_headers = {"Authorization": f"Bearer {login['access_token']}"}

    created = client.post(
        "/admin/api/invites",
        json={"max_seats": 5, "note": "材料报告第 2 批", "expires_in_days": 30},
        headers=admin_headers,
    )
    assert created.status_code == 200
    code = created.json()["invite"]["code"]
    code_id = created.json()["invite"]["code_id"]

    # 用新码登录两个设备，再核对列表席位用量。
    _invite_login(client, code, "device-mgmt-01")
    _invite_login(client, code, "device-mgmt-02")
    listing = client.get("/admin/api/invites", headers=admin_headers).json()
    target = next(item for item in listing["invites"] if item["code_id"] == code_id)
    assert target["seats_used"] == 2
    assert target["max_seats"] == 5

    disabled = client.patch(f"/admin/api/invites/{code_id}", json={"status": "disabled"}, headers=admin_headers)
    assert disabled.status_code == 200
    blocked = client.post(
        "/auth/invite/verify",
        json={"invite_code": code, "device_id": "device-mgmt-03"},
        headers={"x-real-ip": "198.51.100.10"},
    )
    assert blocked.status_code == 410

    expanded = client.patch(f"/admin/api/invites/{code_id}", json={"max_seats": 40, "status": "active"}, headers=admin_headers)
    assert expanded.status_code == 200
    assert expanded.json()["invite"]["max_seats"] == 40


def test_auth_me_reports_beta_and_quota(monkeypatch, tmp_path: Path) -> None:
    """/auth/me 携带 beta 状态与试穿额度，前端据此渲染解锁态和余额。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-ME")
    client = TestClient(app)

    invited = _invite_login(client, "PILOT-ME", "device-me-01")
    me = client.get("/auth/me", headers=_bearer(invited)).json()
    assert me["user"]["beta_qualified"] is True
    assert me["quota"]["tryon_remaining_today"] == 30

    normal = _phone_login(client, "13800000004")
    normal_me = client.get("/auth/me", headers=_bearer(normal)).json()
    assert normal_me["user"]["beta_qualified"] is False


def test_guest_unlock_preserves_identity_and_tryon_selection(monkeypatch, tmp_path: Path) -> None:
    """The inline unlock upgrades the guest instead of dropping the selected photo/account."""
    import importlib

    main = importlib.import_module("app.main")
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "PILOT-INLINE")
    client = TestClient(app)
    guest = client.post("/auth/guest").json()
    headers = _bearer(guest)
    seen = []

    def create_job(photo, filename, outfit_id, photo_mode, scene, user_id, *args, **kwargs):
        seen.append((photo, outfit_id, user_id))
        return {"job_id": "test-inline-job", "status": "pending"}

    monkeypatch.setattr(main, "create_outfit_tryon_job", create_job)
    marker = storage.storage_context(guest["user"]["user_id"]).user_root / "selected-photo.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("original photo and preferences", encoding="utf-8")

    def submit():
        return client.post("/selfit/try-on/jobs", headers=headers,
                           files={"person_image": ("my-photo.jpg", b"original-photo", "image/jpeg")},
                           data={"outfit_id": "selected-look", "client_request_id": "same-selection"})

    assert submit().status_code == 403
    assert not seen
    assert client.post("/auth/invite/upgrade", headers=headers,
                       json={"invite_code": "WRONG", "device_id": "inline-device"}).status_code == 400
    assert not seen
    unlocked = client.post("/auth/invite/upgrade", headers=headers,
                           json={"invite_code": "PILOT-INLINE", "device_id": "inline-device"})
    assert unlocked.status_code == 200
    assert unlocked.json()["user"]["user_id"] == guest["user"]["user_id"]
    assert client.get("/auth/me", headers=headers).json()["user"]["beta_qualified"] is True
    assert submit().status_code == 200
    assert seen == [(b"original-photo", "selected-look", guest["user"]["user_id"])]
    assert marker.read_text(encoding="utf-8") == "original photo and preferences"
    recovered = _invite_login(client, "PILOT-INLINE", "inline-device")
    assert recovered["user"]["user_id"] == guest["user"]["user_id"]

from __future__ import annotations

import io
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.selfit_assets as selfit_assets
import app.selfit_onboarding as selfit_onboarding
import app.selfit_photo as selfit_photo
from app.main import app

API = "/api/v1/selfit"


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.headers: dict[str, dict] = {}

    def put_object(self, key: str, content: bytes, headers: dict | None = None) -> None:
        self.objects[key] = content
        self.headers[key] = headers or {}


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 180, 170)).save(buffer, "JPEG")
    return buffer.getvalue()


def _use_tmp_assets(monkeypatch, tmp_path: Path) -> Path:
    store_dir = tmp_path / "outputs" / "selfit_onboarding"
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_DIR", store_dir)
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_STORE_PATH", store_dir / "sessions.json")
    monkeypatch.setattr(selfit_onboarding, "SELFIT_ONBOARDING_ASSET_DIR", store_dir / "assets")
    return store_dir / "assets"


def test_local_asset_store_round_trip(tmp_path: Path) -> None:
    store = selfit_assets.LocalAssetStore(tmp_path / "assets")
    store.save("ses_1/asset_face_x.jpg", b"img", "image/jpeg")
    assert (tmp_path / "assets" / "ses_1" / "asset_face_x.jpg").read_bytes() == b"img"
    assert store.local_path("ses_1/asset_face_x.jpg") is not None
    assert store.local_path("ses_1/missing.jpg") is None
    assert store.public_url("ses_1/asset_face_x.jpg") is None


def test_oss_asset_store_dual_write(tmp_path: Path) -> None:
    bucket = FakeBucket()
    store = selfit_assets.OssAssetStore(tmp_path / "cache", bucket, prefix="selfit/onboarding")
    store.save("ses_1/asset_face_x.jpg", b"img", "image/jpeg")

    # 本地缓存保留（读取路径），OSS 收到带前缀的 key 与内容类型
    assert (tmp_path / "cache" / "ses_1" / "asset_face_x.jpg").read_bytes() == b"img"
    assert bucket.objects["selfit/onboarding/ses_1/asset_face_x.jpg"] == b"img"
    assert bucket.headers["selfit/onboarding/ses_1/asset_face_x.jpg"]["Content-Type"] == "image/jpeg"
    assert store.public_url("ses_1/asset_face_x.jpg") is None

    with_cdn = selfit_assets.OssAssetStore(
        tmp_path / "cache", bucket, prefix="selfit/onboarding", public_base_url="https://cdn.example.com/selfit/"
    )
    assert with_cdn.public_url("ses_1/x.png") == "https://cdn.example.com/selfit/selfit/onboarding/ses_1/x.png"


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body
        self.content_types[(Bucket, Key)] = ContentType


def test_s3_asset_store_dual_write(tmp_path: Path) -> None:
    client = FakeS3Client()
    store = selfit_assets.S3AssetStore(
        tmp_path / "cache", client, "selfit-assets", prefix="selfit/onboarding", public_base_url="https://cdn.example.com"
    )
    store.save("ses_1/asset_face_x.jpg", b"img", "image/jpeg")

    assert (tmp_path / "cache" / "ses_1" / "asset_face_x.jpg").read_bytes() == b"img"
    assert client.objects[("selfit-assets", "selfit/onboarding/ses_1/asset_face_x.jpg")] == b"img"
    assert client.content_types[("selfit-assets", "selfit/onboarding/ses_1/asset_face_x.jpg")] == "image/jpeg"
    assert store.public_url("ses_1/asset_face_x.jpg") == "https://cdn.example.com/selfit/onboarding/ses_1/asset_face_x.jpg"


def test_photo_upload_with_s3_backend(monkeypatch, tmp_path: Path) -> None:
    asset_dir = _use_tmp_assets(monkeypatch, tmp_path)
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)
    monkeypatch.setenv("SELFIT_ASSET_STORE", "s3")
    monkeypatch.setenv("SELFIT_S3_BUCKET", "selfit-assets")
    monkeypatch.setenv("SELFIT_S3_PREFIX", "selfit/test")
    client = FakeS3Client()
    monkeypatch.setattr(selfit_assets, "_s3_client_from_env", lambda: (client, "selfit-assets"))

    http = TestClient(app)
    session_id = http.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    photo = http.post(f"{API}/sessions/{session_id}/photos/face", files={"image": ("a.jpg", _jpeg_bytes())}).json()["photo"]
    assert photo["status"] == "accepted"

    cached = list((asset_dir / session_id).glob("asset_face_*"))
    assert len(cached) == 1
    expected_key = f"selfit/test/{session_id}/{cached[0].name}"
    assert client.objects[("selfit-assets", expected_key)] == cached[0].read_bytes()


def test_photo_upload_with_oss_backend(monkeypatch, tmp_path: Path) -> None:
    asset_dir = _use_tmp_assets(monkeypatch, tmp_path)
    monkeypatch.setattr(selfit_photo, "_inspector", selfit_photo.accept_all_inspector)
    monkeypatch.setenv("SELFIT_ASSET_STORE", "oss")
    monkeypatch.setenv("SELFIT_OSS_PREFIX", "selfit/test")
    bucket = FakeBucket()
    monkeypatch.setattr(selfit_assets, "_oss_bucket_from_env", lambda: bucket)

    client = TestClient(app)
    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    response = client.post(f"{API}/sessions/{session_id}/photos/face", files={"image": ("a.jpg", _jpeg_bytes())})
    photo = response.json()["photo"]
    assert photo["status"] == "accepted"

    # 本地缓存与 OSS 双写均发生
    cached = list((asset_dir / session_id).glob("asset_face_*"))
    assert len(cached) == 1
    expected_key = f"selfit/test/{session_id}/{cached[0].name}"
    assert bucket.objects[expected_key] == cached[0].read_bytes()


def test_share_download_redirects_to_public_url(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_assets(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_ASSET_STORE", "oss")
    monkeypatch.setenv("SELFIT_OSS_PREFIX", "selfit/test")
    monkeypatch.setenv("SELFIT_OSS_PUBLIC_BASE_URL", "https://cdn.example.com")
    bucket = FakeBucket()
    monkeypatch.setattr(selfit_assets, "_oss_bucket_from_env", lambda: bucket)

    client = TestClient(app)
    session_id = client.post(f"{API}/sessions", json={}).json()["session"]["sessionId"]
    job = client.post(f"{API}/sessions/{session_id}/report-jobs", json={}).json()["job"]
    deadline = time.monotonic() + 10
    finished = client.get(f"{API}/report-jobs/{job['jobId']}").json()["job"]
    while finished["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
        time.sleep(0.05)
        finished = client.get(f"{API}/report-jobs/{job['jobId']}").json()["job"]
    assert finished["status"] == "completed"

    asset = client.post(
        f"{API}/reports/{finished['reportId']}/share-assets",
        json={"slideIndex": 0, "channel": "保存单张", "format": "png"},
    ).json()["asset"]

    download = client.get(asset["downloadUrl"], follow_redirects=False)
    assert download.status_code == 302
    assert download.headers["location"].startswith("https://cdn.example.com/selfit/test/shared/share_")
    assert any(key.startswith("selfit/test/shared/share_") for key in bucket.objects)

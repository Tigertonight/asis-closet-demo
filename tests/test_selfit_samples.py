import asyncio
import io
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps

from app import selfit_onboarding as onboarding, selfit_photo, selfit_samples as samples
from app.main import app

API = "/api/v1/selfit"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SELFIT_ONBOARDING_STORE_BACKEND", "json")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_DIR", tmp_path / "onboarding")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_STORE_PATH", tmp_path / "onboarding/sessions.json")
    monkeypatch.setattr(onboarding, "SELFIT_ONBOARDING_ASSET_DIR", tmp_path / "onboarding/assets")
    monkeypatch.setattr(samples, "CACHE_DIR", tmp_path / "samples")


def session(client, gender="female"):
    result = client.post(f"{API}/sessions", json={"onboardingMode": "new"})
    sid = result.json()["session"]["sessionId"]
    if gender:
        assert client.patch(f"{API}/sessions/{sid}/gender", json={"gender": gender}).status_code == 200
    return sid


def select(client, sid, sample_id, kind=None, **kwargs):
    kind = kind or sample_id.split("-")[-1]
    return client.post(f"{API}/sessions/{sid}/photos/{kind}/sample", json={"sampleId": sample_id}, **kwargs)


def stored(sid):
    return onboarding._find_session(onboarding._load_store(), sid)


@pytest.mark.parametrize("sample_id", list(samples.SAMPLES))
def test_original_analysis_unchanged_and_no_user_qa_archive(monkeypatch, sample_id):
    client = TestClient(app)
    sample = samples.SAMPLES[sample_id]
    raw = sample.path.read_bytes()
    with Image.open(io.BytesIO(raw)) as im:
        original = ImageOps.exif_transpose(im).convert("RGB")
    baseline = selfit_photo.attribute_inspector(original, sample.kind)
    assert baseline.accepted
    calls = []

    def inspect(image, kind):
        assert image.size == original.size
        assert image.tobytes() == original.tobytes()
        calls.append(kind)
        return baseline

    monkeypatch.setattr(selfit_photo, "inspect_photo", inspect)
    monkeypatch.setattr(onboarding, "_archive_photo_to_qa", lambda *a: pytest.fail("sample archived as user photo"))
    sid = session(client, sample.gender)
    result = select(client, sid, sample_id)
    assert result.status_code == 200, result.text
    assert result.json()["analysis"] == selfit_photo.public_analysis(baseline.attributes, baseline.notes, sample.kind)
    photo = stored(sid)["photos"][sample.kind]
    path = onboarding.SELFIT_ONBOARDING_ASSET_DIR / sid / (photo["asset_id"] + onboarding.PHOTO_SUPPORTED_FORMATS[photo["format"]])
    assert path.read_bytes() == raw
    assert photo["source"] == "sample" and photo["sample_id"] == sample_id
    # A second visitor reuses real measurements, but owns an independent record.
    second = session(client, sample.gender)
    repeated = select(client, second, sample_id)
    assert repeated.json()["analysis"] == result.json()["analysis"]
    assert second != sid
    second_photo = stored(second)["photos"][sample.kind]
    assert (onboarding.SELFIT_ONBOARDING_ASSET_DIR / second / (second_photo["asset_id"] + onboarding.PHOTO_SUPPORTED_FORMATS[second_photo["format"]])).read_bytes() == raw
    assert calls == [sample.kind]


def test_cache_invalidates_for_algorithm_and_original_changes(monkeypatch, tmp_path):
    from app import attribute_pipeline
    sample = samples.SAMPLES["female-body"]
    with Image.open(sample.path) as image:
        original = image.convert("RGB")
    calls = []
    def inspect(*args):
        calls.append(1)
        return selfit_photo.PhotoInspection(True, attributes={"body_shape": {"label": "梨型"}})
    monkeypatch.setattr(selfit_photo, "inspect_photo", inspect)
    first, fp = samples.inspect_sample(sample, original)
    assert asdict(samples.inspect_sample(sample, original)[0]) == asdict(first)
    assert len(calls) == 1
    monkeypatch.setattr(attribute_pipeline, "PHOTO_ALGORITHM_VERSION", "test-next-version")
    assert samples.inspect_sample(sample, original)[1] != fp
    assert len(calls) == 2
    monkeypatch.setattr(samples, "_ALGORITHM_FILES", [*samples._ALGORITHM_FILES, "next-release-weights"])
    samples.inspect_sample(sample, original)
    assert len(calls) == 3
    monkeypatch.setattr(samples, "SAMPLE_DIR", tmp_path)
    original.save(tmp_path / sample.filename, quality=95)
    assert samples.inspect_sample(sample, original)[1] != fp
    assert len(calls) == 4
    # Transient failures are not persisted.
    monkeypatch.setattr(selfit_photo, "inspect_photo", lambda *a: selfit_photo.PhotoInspection(False, ["face_not_found"]))
    monkeypatch.setattr(attribute_pipeline, "PHOTO_ALGORITHM_VERSION", "test-transient-failure")
    rejected, key = samples.inspect_sample(sample, original)
    assert not rejected.accepted and not (samples.CACHE_DIR / f"{key}.json").exists()


@pytest.mark.parametrize("sample_id", list(samples.SAMPLES))
def test_preview_small_webp_revalidates_and_preserves_original(sample_id):
    sample = samples.SAMPLES[sample_id]
    original_hash = samples.file_digest(sample.path)
    client = TestClient(app)
    response = client.get(f"{API}/sample-photos/{sample_id}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert len(response.content) < 100_000
    with Image.open(io.BytesIO(response.content)) as im:
        assert im.width <= 720 and im.height <= 960
    assert samples.file_digest(sample.path) == original_hash
    assert client.get(f"{API}/sample-photos/{sample_id}/preview", headers={"If-None-Match": response.headers["etag"]}).status_code == 304


def test_selection_validation_ownership_and_idempotency(monkeypatch):
    client = TestClient(app)
    sid = session(client, None)
    assert select(client, sid, "female-face").json()["error"]["code"] == "profile.gender_required"
    client.patch(f"{API}/sessions/{sid}/gender", json={"gender": "female"})
    for sample_id, kind in [("male-face", "face"), ("female-body", "face"), ("https://example.com/photo.png", "face"), ("../../image", "body")]:
        assert select(client, sid, sample_id, kind).status_code == 422
    assert select(client, sid, "female-face", "bad").status_code == 422
    assert client.get(f"{API}/sample-photos/missing/preview").status_code == 404
    monkeypatch.setattr(selfit_photo, "_inspector", lambda *a: selfit_photo.PhotoInspection(True))
    first = select(client, sid, "female-face", headers={"X-Idempotency-Key": "retry"}).json()
    second = select(client, sid, "female-face", headers={"X-Idempotency-Key": "retry"}).json()
    assert first["photo"]["assetId"] == second["photo"]["assetId"]
    assert first["revision"] == second["revision"]
    data = onboarding._load_store()
    onboarding._find_session(data, sid)["user_id"] = "another-account"
    onboarding._write_store(data)
    assert select(client, sid, "female-face", headers={"X-Idempotency-Key": "retry"}).status_code == 404


def test_concurrent_photos_merge_and_gender_change_discards_old_request(monkeypatch):
    client = TestClient(app)
    sid = session(client)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        original_run = onboarding.run_in_threadpool
        async def delayed(func, *args, **kwargs):
            if func is samples.inspect_sample and args[0].kind == "face":
                entered.set()
                await release.wait()
            if func is samples.inspect_sample:
                return selfit_photo.PhotoInspection(True), "test"
            return await original_run(func, *args, **kwargs)
        monkeypatch.setattr(onboarding, "run_in_threadpool", delayed)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            url = f"{API}/sessions/{sid}"
            face = asyncio.create_task(ac.post(url + "/photos/face/sample", json={"sampleId": "female-face"}))
            await entered.wait()
            assert (await ac.post(url + "/photos/body/sample", json={"sampleId": "female-body"})).status_code == 200
            release.set()
            assert (await face).status_code == 200
            assert set(stored(sid)["photos"]) == {"face", "body"}
            entered.clear(); release.clear()
            old = asyncio.create_task(ac.post(url + "/photos/face/sample", json={"sampleId": "female-face"}))
            await entered.wait()
            await ac.patch(url + "/gender", json={"gender": "male"})
            release.set()
            assert (await old).status_code == 409
            assert stored(sid)["gender"] == "male"
    asyncio.run(scenario())


def test_late_sample_cannot_overwrite_a_new_personal_photo(monkeypatch):
    client = TestClient(app)
    sid = session(client)
    monkeypatch.setattr(selfit_photo, "_inspector", lambda *a: selfit_photo.PhotoInspection(True))
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        original_run = onboarding.run_in_threadpool
        async def delayed(func, *args, **kwargs):
            if func is samples.inspect_sample:
                entered.set()
                await release.wait()
                return selfit_photo.PhotoInspection(True), "test"
            return await original_run(func, *args, **kwargs)
        monkeypatch.setattr(onboarding, "run_in_threadpool", delayed)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            url = f"{API}/sessions/{sid}/photos/face"
            old = asyncio.create_task(ac.post(url + "/sample", json={"sampleId": "female-face"}))
            await entered.wait()
            raw = samples.SAMPLES["male-face"].path.read_bytes()
            response = await ac.post(url, files={"image": ("personal.png", raw, "image/png")})
            assert response.status_code == 200
            release.set()
            assert (await old).status_code == 409
            photo = stored(sid)["photos"]["face"]
            assert not photo.get("sample_id")
            assert photo["asset_id"] == response.json()["photo"]["assetId"]
    asyncio.run(scenario())

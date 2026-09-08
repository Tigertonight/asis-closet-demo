from app.selfit_suit import suit_summary, DESCRIPTIONS
from app.selfit_onboarding import MANUAL_FIELDS
from tests.test_selfit_onboarding_api import _use_tmp_store, _create_session, API
from fastapi.testclient import TestClient
from app.main import app


def test_summary_uses_inference_and_manual_override():
    record = {'photos': {'face': {'status': 'accepted', 'attributes': {'face_shape': {'label': '圆脸'}, 'skin_tone': {'label': '暖白肤'}}}}}
    result = suit_summary(record)
    assert result['features'][0]['value'] == '圆脸'
    assert result['features'][0]['source'] == 'photo'
    assert result['features'][2]['value'] is None
    record['manual'] = {'faceShape': '方脸'}
    corrected = suit_summary(record)['features'][0]
    assert corrected['value'] == '方脸'
    assert corrected['source'] == 'manual'
    assert corrected['description'] != result['features'][0]['description']
    assert all(value in DESCRIPTIONS for options in MANUAL_FIELDS.values() for value in options)


def test_suit_endpoint_and_optional_palette(monkeypatch, tmp_path):
    _use_tmp_store(monkeypatch, tmp_path)
    client = TestClient(app)
    session_id = _create_session(client)['session']['sessionId']
    base = f'{API}/sessions/{session_id}'
    assert client.get(base + '/suit').status_code == 200
    assert client.get(base + '/photos/face/preview').status_code == 404
    assert client.patch(base + '/preferences', json={'axes': {'shape': 50, 'energy': 50, 'trend': 50}, 'palette': None}).status_code == 200
    assert client.patch(base + '/preferences', json={'palette': 'mono'}).status_code == 200
    assert client.patch(base + '/preferences', json={'palette': None}).status_code == 200
    assert client.patch(base + '/profile', json={'manual': {'faceShape': '菱形脸'}}).status_code == 200
    feature = client.get(base + '/suit').json()['features'][0]
    assert feature['value'] == '菱形脸' and feature['source'] == 'manual'
    assert '颧骨' in feature['description']


def test_photo_preview_is_oriented_and_strips_metadata(monkeypatch, tmp_path):
    import io
    from PIL import Image
    import app.selfit_photo as photo
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(photo, 'inspect_photo', lambda *args: photo.PhotoInspection(accepted=True))
    monkeypatch.setattr('app.selfit_onboarding._archive_photo_to_qa', lambda *args: None)
    client = TestClient(app)
    session_id = _create_session(client)['session']['sessionId']
    original = Image.new('RGB', (1600, 800), '#b09080')
    exif = Image.Exif(); exif[274] = 6
    payload = io.BytesIO(); original.save(payload, format='JPEG', exif=exif)
    base = f'{API}/sessions/{session_id}/photos/face'
    assert client.post(base, files={'image': ('face.jpg', payload.getvalue(), 'image/jpeg')}).status_code == 200
    result = client.get(base + '/preview')
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    preview = Image.open(io.BytesIO(result.content))
    assert result.headers['content-type'] == 'image/webp'
    assert preview.format == 'WEBP'
    assert preview.size == (600, 1200)
    assert not preview.getexif()


def test_onboarding_flow_and_vibe_semantic_order():
    from pathlib import Path
    import re
    markup = Path('app/static/selfit/index.html').read_text()
    runtime = Path('app/static/selfit/selfit.js').read_text()
    assert 'data-next="like">去认识自己' in markup
    like_button = re.search(r'<button[^>]*id="likeNext"[^>]*>', markup).group()
    assert 'disabled' not in like_button
    expression = re.search(r'<fieldset data-question="expression">(.*?)</fieldset>', markup).group(1)
    assert re.findall(r'data-answer="([A-E])"', expression) == ['A', 'B', 'E', 'D', 'C']
    assert 'id="suitResultPhotos"' in markup and 'id="suitFeatures"' in markup
    assert "showScreen('suit-processing')" in runtime
    assert "await delay(650);\n      document.querySelector('#continueToApp')" in runtime
    assert "showScreen('report');" in runtime


def test_saved_suit_photos_are_scoped_to_session_owner():
    from app.selfit_onboarding import _suit_photo
    saved = {'session_id': 'old', 'asset_id': 'asset_face', 'format': 'JPEG'}
    data = {'user_photos': [{'user_id': 'alice', 'photos': {'face': saved}}], 'sessions': []}
    assert _suit_photo(data, {'session_id': 'new', 'user_id': 'alice'}, 'face') == saved
    assert _suit_photo(data, {'session_id': 'new', 'user_id': 'bob'}, 'face') is None
    assert _suit_photo(data, {'session_id': 'new'}, 'face') is None
    current = {'status': 'accepted', 'asset_id': 'new_face', 'format': 'PNG'}
    assert _suit_photo(data, {'session_id': 'new', 'user_id': 'alice', 'photos': {'face': current}}, 'face')['asset_id'] == 'new_face'


def test_new_session_loads_own_saved_photo_as_webp(monkeypatch, tmp_path):
    import io
    from PIL import Image
    import app.selfit_onboarding as onboarding
    import app.selfit_photo as photo
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(photo, 'inspect_photo', lambda *args: photo.PhotoInspection(accepted=True))
    monkeypatch.setattr(onboarding, '_archive_photo_to_qa', lambda *args: None)
    app.dependency_overrides[onboarding.get_optional_user] = lambda: {'user_id': 'photo-owner'}
    try:
        client = TestClient(app)
        original = _create_session(client)['session']['sessionId']
        content = io.BytesIO(); Image.new('RGB', (600, 800), '#a08070').save(content, 'PNG')
        assert client.post(f'{API}/sessions/{original}/photos/face', files={'image': ('face.png', content.getvalue(), 'image/png')}).status_code == 200
        current = _create_session(client)['session']['sessionId']
        assert client.get(f'{API}/sessions/{current}/suit').json()['photos']['face'] is True
        result = client.get(f'{API}/sessions/{current}/photos/face/preview')
        assert result.status_code == 200 and result.headers['content-type'] == 'image/webp'
        assert Image.open(io.BytesIO(result.content)).format == 'WEBP'
        app.dependency_overrides[onboarding.get_optional_user] = lambda: {'user_id': 'another-owner'}
        assert client.get(f'{API}/sessions/{current}/photos/face/preview').status_code in (403, 404)
    finally:
        app.dependency_overrides.pop(onboarding.get_optional_user, None)


def test_consumer_overlay_retains_detected_lines_without_qa_banner(monkeypatch):
    from PIL import Image
    from app import qa_onboarding
    monkeypatch.setattr(qa_onboarding, 'debug_face_geometry', lambda image: {
        'lines': [{'name': '脸长', 'from': [50, 30], 'to': [50, 80], 'width': 50}],
        'points': {}, 'skin_regions': [],
    })
    result = qa_onboarding._render_face_overlay(Image.new('RGB', (100, 100), 'white'), {}, include_details=False)
    assert result.getpixel((50, 50)) == (147, 51, 234)
    assert result.getpixel((5, 5)) == (255, 255, 255)


def test_upload_replaces_previous_choices_and_edits_only_change_one_source(monkeypatch, tmp_path):
    import io
    from PIL import Image
    import app.selfit_photo as photo
    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setattr(photo, 'inspect_photo', lambda *args: photo.PhotoInspection(accepted=True, attributes={
        'face_shape': {'label': '椭圆脸'}, 'skin_tone': {'label': '暖白肤'},
    }))
    monkeypatch.setattr('app.selfit_onboarding._archive_photo_to_qa', lambda *args: None)
    client = TestClient(app)
    base = f"{API}/sessions/{_create_session(client)['session']['sessionId']}"
    client.patch(base + '/profile', json={'manual': {'faceShape': '圆脸', 'skin': '冷白肤', 'bodyShape': '梨型'}})
    content = io.BytesIO(); Image.new('RGB', (600, 800), '#a08070').save(content, 'PNG')
    assert client.post(base + '/photos/face', files={'image': ('face.png', content.getvalue(), 'image/png')}).status_code == 200
    features = client.get(base + '/suit').json()['features']
    assert [(x['value'], x['source']) for x in features] == [('椭圆脸', 'photo'), ('暖白肤', 'photo'), ('梨型', 'manual')]
    client.patch(base + '/profile', json={'manual': {'faceShape': '方脸'}})
    features = client.get(base + '/suit').json()['features']
    assert [(x['value'], x['source']) for x in features[:2]] == [('方脸', 'manual'), ('暖白肤', 'photo')]

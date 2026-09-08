import pytest

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


def test_photo_analysis_handles_missing_and_legacy_attributes():
    assert all(feature['photoAnalysis'] is None for feature in suit_summary({})['features'])
    record = {'photos': {'face': {'status': 'accepted', 'attributes': {
        'face_shape': {'label': '椭圆脸', 'confidence': 0.0},
        'skin_tone': {'label': '中性自然肤'},
    }}}}
    face, skin, body = suit_summary(record)['features']
    assert face['photoAnalysis'] == {
        'label': '椭圆脸', 'confidence': 0.0, 'candidates': [],
        'metrics': {'lengthWidthRatio': None, 'jawCheekRatio': None, 'foreheadCheekRatio': None},
    }
    assert skin['photoAnalysis'] == {
        'label': '中性自然肤', 'confidence': None, 'metrics': {'lStar': None, 'itaDegrees': None},
    }
    assert body['photoAnalysis'] is None
    record['photos']['face']['status'] = 'rejected'
    assert all(feature['photoAnalysis'] is None for feature in suit_summary(record)['features'])


@pytest.mark.parametrize('backend', ['json', 'sqlite'])
def test_suit_returns_saved_measurements_and_keeps_manual_labels_separate(monkeypatch, tmp_path, backend):
    import io
    from copy import deepcopy
    from PIL import Image
    import app.attribute_pipeline as pipeline
    import app.selfit_photo as photo

    _use_tmp_store(monkeypatch, tmp_path)
    monkeypatch.setenv('SELFIT_ONBOARDING_STORE_BACKEND', backend)
    calls = []
    face_result = {'status': 'pass', 'issues': [], 'attributes': {
        'face_shape': {
            'status': 'pass', 'label': '椭圆脸', 'confidence': 0.76,
            'candidates': [{'label': '椭圆脸', 'score': 0.58}, {'label': '心形脸', 'score': 0.406}],
            'evidence': {'method': 'internal', 'features': {
                'length_width_ratio': 1.281, 'jaw_cheek_ratio': 0.738,
                'forehead_cheek_ratio': 1.036, 'jaw_angle_deg': 120,
            }},
        },
        'skin_tone': {
            'status': 'pass', 'label': '中性自然肤', 'confidence': 0.72,
            'evidence': {'l_star': 65.17, 'ita_deg': 52.6, 'rgb': [150, 130, 120]},
        },
    }}

    def analyze_face(image):
        calls.append('face')
        return deepcopy(face_result)

    def analyze_body(image):
        calls.append('body')
        return {'status': 'pass', 'issues': [], 'attributes': {
            'body_shape': {'status': 'pass', 'label': '梨型', 'confidence': 0.68},
        }}

    monkeypatch.setattr(pipeline, 'analyze_face_photo', analyze_face)
    monkeypatch.setattr(pipeline, 'analyze_body_photo', analyze_body)
    monkeypatch.setattr(photo, 'inspect_photo', photo.attribute_inspector)
    monkeypatch.setattr('app.selfit_onboarding._archive_photo_to_qa', lambda *args: None)
    client = TestClient(app)
    base = f"{API}/sessions/{_create_session(client)['session']['sessionId']}"
    image = io.BytesIO()
    Image.new('RGB', (600, 800), '#a08070').save(image, 'PNG')

    def upload(kind):
        response = client.post(base + '/photos/' + kind, files={'image': ('photo.png', image.getvalue(), 'image/png')})
        assert response.status_code == 200
        assert response.json()['photo']['status'] == 'accepted'
        assert set(response.json()['photo']) == {'kind', 'assetId', 'status', 'code', 'message', 'issues'}

    upload('face')
    upload('body')
    response = client.get(base + '/suit')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['photos'] == {'face': True, 'body': True}
    face, skin, body = response.json()['features']
    assert face['photoAnalysis'] == {
        'label': '椭圆脸', 'confidence': 0.76,
        'candidates': [{'label': '椭圆脸', 'score': 0.58}, {'label': '心形脸', 'score': 0.406}],
        'metrics': {'lengthWidthRatio': 1.281, 'jawCheekRatio': 0.738, 'foreheadCheekRatio': 1.036},
    }
    assert skin['photoAnalysis'] == {
        'label': '中性自然肤', 'confidence': 0.72, 'metrics': {'lStar': 65.17, 'itaDegrees': 52.6},
    }
    assert body['photoAnalysis'] == {'label': '梨型', 'confidence': 0.68}
    assert client.patch(base + '/profile', json={'manual': {'faceShape': '方脸', 'skin': '暖白肤'}}).status_code == 200
    corrected = client.get(base + '/suit').json()['features']
    assert [(item['value'], item['source']) for item in corrected[:2]] == [('方脸', 'manual'), ('暖白肤', 'manual')]
    assert [item['photoAnalysis'] for item in corrected] == [item['photoAnalysis'] for item in (face, skin, body)]
    assert calls == ['face', 'body']  # GET and manual edits consume saved values without running detection.

    # A replacement face whose shape is unrecognizable must not reuse the old candidates/ratios.
    face_result['attributes']['face_shape'] = {'status': 'warn', 'label': None, 'confidence': 0.4}
    face_result['attributes']['skin_tone']['evidence'] = {'l_star': 64.0, 'ita_deg': 0.0}
    upload('face')
    replaced = client.get(base + '/suit').json()['features']
    assert replaced[0]['value'] is None and replaced[0]['photoAnalysis'] is None
    assert replaced[1]['value'] == '中性自然肤' and replaced[1]['source'] == 'photo'
    assert replaced[1]['photoAnalysis']['metrics'] == {'lStar': 64.0, 'itaDegrees': 0.0}
    assert replaced[2]['photoAnalysis'] == body['photoAnalysis']


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

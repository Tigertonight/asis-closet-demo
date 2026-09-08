from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user
from app import selfit_inspiration as inspiration, storage


def test_catalog_notes_have_real_assets_and_persona_scoped_ids():
    ids = set()
    for persona in inspiration._personality_template_catalog()['types']:
        notes = inspiration.persona_notes(persona)
        assert len(notes) == 4
        for note in notes:
            assert note['id'] not in ids
            ids.add(note['id'])
            assert note['kind'] == 'note' and 'item_ids' not in note
            asset = Path('app') / urlsplit(note['image_url']).path.lstrip('/')
            assert asset.is_file(), asset
            assert note['width'] > 0 and note['height'] > 0
            assert not note['source_url'] or note['source_url'].startswith('https://')


def test_notes_use_account_persona_and_favorites_are_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    personas = {'alice':'mute','bob':'flou'}
    monkeypatch.setattr(inspiration, 'resolve_profile', lambda user: {'persona_id': personas.get(user)})
    client = TestClient(app)
    assert client.get('/selfit/try-on/inspiration-notes').status_code == 401
    user = {'user_id': 'alice'}
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        endpoint = '/selfit/try-on/inspiration-notes'
        result = client.get(endpoint+'?persona=flou').json()
        assert result['persona'] == 'mute'
        note_id = result['notes'][0]['id']
        favorite = f'{endpoint}/{note_id}/favorite'
        assert client.patch(favorite,json={'favorite':True}).status_code == 200
        assert client.get(endpoint).json()['notes'][0]['favorite'] is True
        assert client.get(endpoint).json()['saved_notes'][0]['id'] == note_id
        assert client.patch(favorite,json={'favorite':'yes'}).status_code == 422
        user['user_id'] = 'bob'
        assert all(not note['favorite'] for note in client.get(endpoint).json()['notes'])
        assert client.get(endpoint).json()['saved_notes'] == []
        assert client.patch(favorite,json={'favorite':False}).status_code == 404
        user['user_id'] = 'alice'
        assert client.get(endpoint).json()['notes'][0]['favorite'] is True
        personas['alice'] = 'iced'
        assert client.get(endpoint).json()['saved_notes'][0]['id'] == note_id
        assert client.get(endpoint).json()['notes'][0]['persona'] == 'iced'
        assert client.patch(favorite,json={'favorite':False}).status_code == 200
        assert client.get(endpoint).json()['saved_notes'] == []
        assert client.patch(favorite,json={'favorite':True}).status_code == 404
        assert client.get(endpoint).json()['notes'][0]['favorite'] is False
        user['user_id'] = 'untested'
        assert client.get(endpoint).json()['notes'] == []
        assert client.get(endpoint).json()['profile_required'] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)

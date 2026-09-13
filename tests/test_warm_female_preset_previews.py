import hashlib
from copy import deepcopy

import pytest

from scripts import warm_female_preset_previews as warmer


def fixture_data(tmp_path, monkeypatch):
    data = b'verified cached preview'
    digest = hashlib.sha256(data).hexdigest()
    target = tmp_path/'preview.webp'
    target.write_bytes(data)
    calls = []
    def cached(asset_id, registry):
        calls.append(asset_id)
        return target
    monkeypatch.setattr(warmer, 'material_image_path', cached)
    row = {'id': 'female-one', 'model': {'gender': 'female'}, 'status': 'uploaded',
           'strategy': 'complete_outfit_single_call', 'result': {'sha256': 'source'},
           'displayResult': {'verified': True, 'sourceSha256': 'source', 'sha256': digest, 'assetId': 'asset_'+digest}}
    class Registry:
        def get(self, asset_id):
            assert asset_id == 'asset_'+digest
            return {'sha256': digest, 'contentType': 'image/webp'}
    return {'examples': [row]}, Registry(), target, calls


def test_warms_only_verified_female_previews_and_rechecks_cached_bytes(tmp_path, monkeypatch):
    index, registry, target, calls = fixture_data(tmp_path, monkeypatch)
    index['examples'].append({'id': 'existing-male', 'model': {'gender': 'male'}})
    result = warmer.warm(index, registry, expected=1)
    assert result == {'cachedPreviews': 1, 'bytes': target.stat().st_size, 'sha256Verified': True}
    assert len(calls) == 1
    target.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='cache mismatch'):
        warmer.warm(index, registry, expected=1)


@pytest.mark.parametrize('invalid', ['count', 'duplicate', 'status', 'source', 'verification', 'digest'])
def test_rejects_incomplete_or_mismatched_data_before_fetch(tmp_path, monkeypatch, invalid):
    index, registry, _, calls = fixture_data(tmp_path, monkeypatch)
    row = index['examples'][0]
    if invalid == 'count': index['examples'] = []
    if invalid == 'duplicate': index['examples'].append(deepcopy(row))
    if invalid == 'status': row['status'] = 'generated_local'
    if invalid == 'source': row['displayResult']['sourceSha256'] = 'other'
    if invalid == 'verification': row['displayResult']['verified'] = False
    if invalid == 'digest': row['displayResult']['sha256'] = 'other'
    with pytest.raises(ValueError):
        warmer.warm(index, registry, expected=2 if invalid == 'duplicate' else 1)
    assert calls == []

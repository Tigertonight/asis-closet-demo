from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import closet, storage, tryon
from app.auth import get_current_user
from app.beta_access import require_beta_tryon, require_beta_user
from app.main import app


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'ROOT_DIR', tmp_path)
    image_path = tmp_path / 'fixture.png'
    Image.new('RGB', (720, 1200), '#dfd9d5').save(image_path)
    person = tryon._read_upload_image(image_path.read_bytes(), 'fixture.png', 'person')
    slots = ['top', 'bottom', 'shoes', 'bag']
    plan = {'title': 'all items', 'items': [
        {'item_id': slot, 'slot': slot, 'category': slot, 'image_path': str(image_path)} for slot in slots
    ]}
    pass_stage = lambda: tryon._stage('pass', 0.9, {}, [])
    monkeypatch.setattr(tryon, '_input_quality_stage', lambda *_: pass_stage())
    monkeypatch.setattr(tryon, '_detect_person', lambda _: tryon._stage('pass', 0.9, {
        'primary_face': {'box': {'x': 240, 'y': 60, 'width': 150, 'height': 180}},
    }, []))
    # Actual coverage heuristic sees the upper/lower body but excludes shoes.
    edited = []

    def mask(image, detection, items, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('L', image.size, 255).save(path)
        return tryon._stage('pass', 0.9, {'mask_path': str(path)}, [])

    def edit(**kwargs):
        edited.append([item['item_id'] for item in kwargs['plan']['items']])
        return {'stage': pass_stage(), 'image_path': image_path}

    monkeypatch.setattr(tryon, '_generate_outfit_group_mask', mask)
    monkeypatch.setattr(tryon, '_run_staged_outfit_edit', edit)
    monkeypatch.setattr(tryon, '_review_outfit_tryon_quality', lambda *_args, **_kwargs: pass_stage())
    monkeypatch.setattr(tryon, '_default_provider', lambda: object())
    return person, plan, edited


def test_full_outfit_keeps_shoes_in_generation_and_uses_separate_cache(pipeline):
    person, plan, edited = pipeline
    default = tryon.run_try_on_from_outfit_plan(person, plan, provider=object())
    assert default['skipped_item_ids'] == ['shoes']
    full = tryon.run_try_on_from_outfit_plan(person, plan, provider=object(),
        selected_item_ids=['top', 'bottom', 'shoes', 'bag'], wear_all_items=True)
    assert edited[-1] == ['top', 'bottom', 'shoes', 'bag']
    assert full['requested_item_ids'] == full['applied_item_ids'] == edited[-1]
    assert full['skipped_item_ids'] == full['user_skipped_item_ids'] == []
    assert full['pipeline']['body_coverage']['evidence']['unverified_slots'] == ['shoes']
    assert full['pipeline']['body_coverage']['evidence']['skipped_slots'] == []
    assert not any('已跳过' in issue['message'] for issue in full['decision']['warnings'])
    assert default['tryon_id'] != full['tryon_id'], 'do not reuse a partial outfit result'


def test_missing_item_cannot_silently_be_omitted_from_full_outfit(pipeline):
    person, plan, _ = pipeline
    with pytest.raises(HTTPException, match='套装中有单品暂时无法试穿'):
        tryon.run_try_on_from_outfit_plan(person, plan, provider=object(),
            selected_item_ids=['top', 'bottom', 'shoes', 'bag', 'missing'], wear_all_items=True)


@pytest.mark.parametrize('item_count', [4, 14])
def test_job_endpoint_and_retry_preserve_full_outfit_mode(monkeypatch, pipeline, item_count):
    person, plan, edited = pipeline
    if item_count > 4:
        plan['items'].extend({**plan['items'][-1], 'item_id': f'accessory-{i}', 'slot': 'accessory', 'category': 'accessory'} for i in range(item_count - 4))
    expected_ids = [i['item_id'] for i in plan['items']]
    monkeypatch.setattr(closet, 'outfit_as_tryon_plan', lambda *_args, **_kwargs: (plan, {'outfit_id': 'set-a'}))
    monkeypatch.setattr(closet, 'record_selfit_tryon_result', lambda *_: None)

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(tryon, 'TRYON_JOB_EXECUTOR', ImmediateExecutor())
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'direct-tryon-test'}
    app.dependency_overrides[require_beta_user] = lambda: {'user_id': 'direct-tryon-test', 'beta_qualified': True}
    app.dependency_overrides[require_beta_tryon] = lambda: {'user_id': 'direct-tryon-test', 'beta_qualified': True}
    try:
        client = TestClient(app)
        import json
        data = {'outfit_id': 'set-a', 'selected_item_ids': json.dumps(expected_ids),
                'wear_all_items': 'true', 'client_request_id': 'direct-all-items'}
        files = {'person_image': ('person.png', Path(person['saved_path']).read_bytes(), 'image/png')}
        created = client.post('/selfit/try-on/jobs', data=data, files=files)
        assert created.status_code == 200, created.text
        job_id = created.json()['job_id']
        assert created.json()['wear_all_items'] is True
        result = client.get(f'/selfit/try-on/jobs/{job_id}').json()
        assert result['status'] == 'completed', result
        assert result['result']['applied_item_ids'] == expected_ids
        assert client.post('/selfit/try-on/jobs', data=data, files=files).json()['job_id'] == job_id
        assert len(edited) == 1
        assert client.post(f'/selfit/try-on/jobs/{job_id}/retry').status_code == 200
        assert edited[-1] == expected_ids
        assert client.get(f'/selfit/try-on/jobs/{job_id}').json()['wear_all_items'] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_beta_user, None)
        app.dependency_overrides.pop(require_beta_tryon, None)


def test_delivered_dress_and_trousers_keep_intentional_layering(pipeline):
    person, plan, edited = pipeline
    plan['items'][0].update(slot='dress', category='dress')
    with pytest.raises(HTTPException, match='连衣装与上下装'):
        tryon.run_try_on_from_outfit_plan(person, plan, provider=object(), wear_all_items=True)
    plan.update(source_catalog='styling_delivery', layer_sequence_inner_to_outer=[i['item_id'] for i in plan['items']])
    result = tryon.run_try_on_from_outfit_plan(person, plan, provider=object(), wear_all_items=True)
    assert result['applied_item_ids'] == [i['item_id'] for i in plan['items']]

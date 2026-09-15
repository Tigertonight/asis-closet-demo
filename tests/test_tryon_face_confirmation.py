import numpy as np
from PIL import Image
from app import tryon, cv_pipeline


def face(x, y):
    return {'box': {'x': x, 'y': y, 'width': 100, 'height': 100}, 'area_ratio': .01, 'detector': 'haar_frontal'}


def verifier(monkeypatch, answers):
    monkeypatch.setattr(cv_pipeline, '_mediapipe_face_detector', lambda: object())
    responses = iter(answers)
    def detect(*args, **kwargs):
        answer = next(responses)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(cv_pipeline, '_detect_mediapipe_face_candidates', detect)


MATCH = [(30, 30, 100, 100, 'mediapipe_tasks_0.95')]


def test_background_is_removed_but_detected_geometry_is_preserved(monkeypatch):
    verifier(monkeypatch, [[], MATCH, []])
    faces = [face(200, 50), face(400, 250), face(700, 600)]
    confirmed, rejected = tryon._confirm_face_candidates(np.zeros((1000, 1000, 3), dtype=np.uint8), faces)
    assert confirmed == [{**faces[1], "verified_by": "mediapipe_candidate_crop"}]
    assert rejected == [faces[0], faces[2]]


def test_multiple_confirmed_people_still_block(monkeypatch):
    verifier(monkeypatch, [MATCH, MATCH, []])
    class Detector:
        def detectMultiScale(self, *args, **kwargs):
            return [(200, 100, 100, 100), (500, 120, 100, 100), (700, 600, 100, 100)]
    monkeypatch.setattr(tryon.cv2, 'CascadeClassifier', lambda _: Detector())
    result = tryon._detect_person(Image.new('RGB', (1000, 1000)))
    assert result['status'] == 'fail'
    assert result['issues'][0]['code'] == 'person.multiple_faces'
    assert result['evidence']['face_count'] == 2


def test_verifier_failure_or_no_matches_never_silently_drops_faces(monkeypatch):
    faces = [face(100, 100), face(400, 100)]
    image = np.zeros((800, 800, 3), dtype=np.uint8)
    for answers in ([MATCH, RuntimeError('unavailable')], [[], []]):
        verifier(monkeypatch, answers)
        assert tryon._confirm_face_candidates(image, faces) == (faces, [])
    monkeypatch.setattr(cv_pipeline, '_mediapipe_face_detector', lambda: None)
    assert tryon._confirm_face_candidates(image, faces) == (faces, [])


def test_confirmed_lower_person_is_not_treated_as_a_prop(monkeypatch):
    verifier(monkeypatch, [MATCH, MATCH])
    class Detector:
        def detectMultiScale(self, *args, **kwargs):
            return [(200, 100, 100, 100), (200, 750, 100, 100)]
    monkeypatch.setattr(tryon.cv2, 'CascadeClassifier', lambda _: Detector())
    monkeypatch.setattr(tryon, '_lower_face_like_props', lambda faces, h: faces[1:])
    result = tryon._detect_person(Image.new('RGB', (1000, 1000)))
    assert result['status'] == 'fail'
    assert result['issues'][0]['code'] == 'person.multiple_faces'

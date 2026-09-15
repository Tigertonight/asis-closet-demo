import numpy as np
from PIL import Image
from app.face_restore import FaceRestorer


def fixture(monkeypatch):
    rng = np.random.default_rng(10)
    pixels = rng.integers(80,180,(256,256,3),dtype=np.uint8)
    face = {'evidence':{'primary_face':{'box':dict(x=64,y=64,width=128,height=128)}}}
    angles = np.linspace(0,2*np.pi,468,endpoint=False)
    points = np.column_stack([128+50*np.cos(angles),128+65*np.sin(angles)]).astype(np.float32)
    from app.face_restore import _OVAL
    for idx,angle in zip(_OVAL,np.linspace(0,2*np.pi,len(_OVAL),endpoint=False)):
        points[idx]=[128+50*np.cos(angle),128+65*np.sin(angle)]
    monkeypatch.setattr(FaceRestorer,'landmarks',staticmethod(lambda _:points.copy()))
    return Image.fromarray(pixels),face


def test_restore_preserves_surroundings_and_source_detail(monkeypatch,tmp_path):
    original,face=fixture(monkeypatch)
    target=Image.new('RGB',original.size,(130,130,130));path=tmp_path/'result.png';target.save(path)
    path,e=FaceRestorer(original,face).restore(path,tmp_path/'restored.png')
    assert e['applied']
    restored=np.array(Image.open(path));source=np.array(original)
    assert np.all(restored[:40]==130)
    assert np.all(restored[210:]==130)
    assert np.mean(abs(restored[110:145,110:145].astype(float)-source[110:145,110:145]))<5


def test_restore_skips_missing_landmarks_and_changed_canvas(monkeypatch,tmp_path):
    original,face=fixture(monkeypatch)
    path=tmp_path/'result.png';original.save(path)
    monkeypatch.setattr(FaceRestorer,'landmarks',staticmethod(lambda _:None))
    output,e=FaceRestorer(original,face).restore(path,tmp_path/'restored.png')
    assert output==path and not e['applied']
    Image.new('RGB',(128,128)).save(path)
    _,e=FaceRestorer(original,face).restore(path,tmp_path/'restored.png')
    assert e['reason']=='canvas_changed'


def test_restore_rejects_large_movement(monkeypatch,tmp_path):
    original,face=fixture(monkeypatch);r=FaceRestorer(original,face);r.prepare()
    points=r.points.copy()+40
    monkeypatch.setattr(FaceRestorer,'landmarks',staticmethod(lambda _:points))
    path=tmp_path/'result.png';original.save(path)
    _,e=r.restore(path,tmp_path/'restored.png')
    assert not e['applied'] and e['reason']=='pose_changed'


def test_restore_never_waits_for_preparation(monkeypatch,tmp_path):
    from concurrent.futures import Future
    original,face=fixture(monkeypatch)
    r=FaceRestorer(original,face);r.preparation=Future()
    path=tmp_path/'result.png';original.save(path)
    output,e=r.restore(path,tmp_path/'restored.png')
    assert output==path and e['reason']=='preparation_not_ready'

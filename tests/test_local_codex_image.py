import json
import os
from pathlib import Path
import subprocess
import time

import pytest
from fastapi import HTTPException
from PIL import Image

from app import local_codex_image as bridge, tryon


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv('TRYON_LOCAL_CODEX_BRIDGE', '1')
    monkeypatch.setenv('SELFIT_ENV', 'local')
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', '0')
    monkeypatch.delenv('SELFIT_CODEX_IMAGE_MODEL', raising=False)
    monkeypatch.setattr(bridge, '_binary', lambda: '/test/codex')
    paths = []
    for i in range(3):
        path = tmp_path / f'input-{i}.png'
        Image.new('RGB', (256, 384), (20 * i, 60, 90)).save(path)
        paths.append(path)
    return paths


def test_local_override_wins_without_probing_remote_services(local, monkeypatch):
    monkeypatch.setattr(tryon, '_has_runway_google_provider', lambda: pytest.fail('unneeded remote provider probe'))
    assert isinstance(tryon._default_provider(), tryon.LocalCodexImageGenTryOnProvider)


def test_capabilities_identify_the_active_local_bridge(local, monkeypatch):
    monkeypatch.setattr(tryon, '_openai_base_url', lambda: None)
    monkeypatch.setattr(tryon, '_has_runway_google_provider', lambda: True)
    capabilities = tryon.tryon_capabilities()
    assert capabilities['features']['image_edit'] == bridge.MODE
    assert capabilities['provider']['local_codex_bridge_enabled'] is True
    assert '本地 Codex 试穿桥接已启用' in capabilities['message']


@pytest.mark.parametrize('mode,public', [('production','0'), ('demo','0'), ('staging','0'), ('local','1')])
def test_public_environment_never_launches_local_codex(local, monkeypatch, tmp_path, mode, public):
    monkeypatch.setenv('SELFIT_ENV', mode)
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', public)
    monkeypatch.setattr(bridge.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not spawn'))
    monkeypatch.setattr(tryon, '_has_runway_google_provider', lambda: False)
    monkeypatch.setattr(tryon, '_has_openai_image_edit_provider', lambda: False)
    monkeypatch.delenv('TRYON_ENABLE_PI_AGENT_CODE_WORKER', raising=False)
    assert isinstance(tryon._default_provider(), tryon.UnavailableTryOnProvider)
    with pytest.raises(HTTPException) as error:
        bridge.generate_image(*local, 'prompt', tmp_path / 'output')
    assert error.value.status_code == 503


def test_completed_image_is_copied_before_temporary_workspace_disappears(local, monkeypatch, tmp_path):
    calls = []
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            self.command, self.workspace = command, kwargs['cwd']
            calls.append((command, kwargs))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, prompt, timeout):
            assert 'exactly once' in prompt and 'stage-specific prompt' in prompt
            assert timeout == 900
            result = self.workspace / 'native-generated.png'
            Image.new('RGB', (256, 384), (130, 20, 60)).save(result)
            Path(self.command[self.command.index('--output-last-message') + 1]).write_text(json.dumps({'image_path':str(result), 'error':''}))
    monkeypatch.setattr(bridge.subprocess, 'Popen', Process)
    output, evidence = bridge.generate_image(*local, 'stage-specific prompt', tmp_path / 'output')
    assert output.exists() and Image.open(output).size == (256, 384)
    command, options = calls[0]
    attached = [Path(command[i+1]) for i,x in enumerate(command) if x == '--image']
    assert attached[:2] == local[:2]
    assert attached[2].name == 'mask-guide.png' and Image.open(attached[2]).mode == 'RGB'
    assert command[command.index('--enable')+1] == 'image_generation'
    assert command[command.index('--sandbox')+1] == 'read-only'
    assert not options.get('shell') and options['start_new_session']
    assert '--model' not in command and not options['cwd'].exists()
    assert json.loads(Path(evidence['requestPath']).read_text())['status'] == 'completed'


def test_rgba_mask_is_transmitted_as_visible_alpha_guide(local, monkeypatch, tmp_path):
    mask = Image.new('RGBA', (256,384), (255,255,255,255))
    mask.putpixel((20,20), (255,255,255,0))
    mask.save(local[2])
    def inspect(command, **kwargs):
        guide = Path([command[i+1] for i,x in enumerate(command) if x == '--image'][-1])
        image = Image.open(guide)
        assert image.getpixel((20,20)) == (0,0,0)
        assert image.getpixel((0,0)) == (255,255,255)
        raise OSError('test stops before generation')
    monkeypatch.setattr(bridge.subprocess, 'Popen', inspect)
    with pytest.raises(HTTPException):
        bridge.generate_image(*local, 'prompt', tmp_path / 'output')


@pytest.mark.parametrize('failure,status', [('exit',503), ('timeout',504), ('missing',502), ('bad_path',502)])
def test_failed_process_and_invalid_results_are_terminal_and_sanitized(local, monkeypatch, tmp_path, failure, status):
    killed = []
    class Process:
        pid = 123456
        returncode = 1 if failure == 'exit' else 0
        def __init__(self, command, **kwargs): self.command = command
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, *args, **kwargs):
            if failure == 'timeout' and args: raise subprocess.TimeoutExpired('codex', 900)
            Path(self.command[self.command.index('--output-last-message') + 1]).write_text(json.dumps({
                'image_path': '/private/credentials.png' if failure == 'bad_path' else '', 'error':'raw secret' if failure == 'missing' else ''}))
    monkeypatch.setattr(bridge.subprocess, 'Popen', Process)
    monkeypatch.setattr(bridge.os, 'killpg', lambda *args: killed.append(args))
    with pytest.raises(HTTPException) as error:
        bridge.generate_image(*local, 'prompt', tmp_path / 'output')
    assert error.value.status_code == status
    assert 'secret' not in str(error.value.detail) and 'credentials' not in str(error.value.detail)
    assert bool(killed) == (failure == 'timeout')
    request = next((tmp_path / 'output').rglob('request.json'))
    assert json.loads(request.read_text())['status'] == 'failed'


def test_stale_input_or_unrelated_output_is_rejected(local, tmp_path):
    workspace = tmp_path / 'work'; workspace.mkdir()
    result = workspace / 'output.png'
    Image.new('RGB', (256,384), 'red').save(result)
    started = time.time()
    os.utime(result, (started-60, started-60))
    with pytest.raises(ValueError): bridge._validated_output(str(result), workspace, started, local)
    with pytest.raises(ValueError): bridge._validated_output(str(local[0]), tmp_path, started, local)


def test_provider_waits_and_returns_image_or_useful_failure(local, monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, 'generate_image', lambda *args: (local[1], {'provider':bridge.MODE}))
    result = tryon.LocalCodexImageGenTryOnProvider().edit(*local, 'prompt', tmp_path)
    assert result['stage']['status'] == 'pass' and result['image_path'].exists()
    def failed(*args): raise HTTPException(504, '这次试穿生成超时，请稍后重试。')
    monkeypatch.setattr(bridge, 'generate_image', failed)
    result = tryon.LocalCodexImageGenTryOnProvider().edit(*local, 'prompt', tmp_path)
    assert result['stage']['status'] == 'fail' and result['image_path'] is None
    assert result['stage']['issues'][0]['code'] == 'image_edit.local_codex_failed'


def test_outfit_failure_preserves_generation_error_instead_of_quality_error(local, monkeypatch, tmp_path):
    person_path = Path(__file__).parent / 'fixtures' / 'tryon_models' / 'female_medium_1.png'
    person = tryon._read_upload_image(person_path.read_bytes(), person_path.name, 'person')
    plan = {'title': 'local bridge failure', 'items': [
        {'item_id': 'top', 'slot': 'top', 'category': 'top', 'image_path': str(local[1])}]}
    monkeypatch.setattr(tryon, '_tryon_output_dir', lambda: tmp_path / 'tryon')
    def failed(*args):
        raise HTTPException(504, '这次试穿生成超时，请稍后重试。')
    monkeypatch.setattr(bridge, 'generate_image', failed)
    monkeypatch.setattr(tryon, '_review_outfit_tryon_quality', lambda *args: pytest.fail('no image to review'))
    result = tryon.run_try_on_from_outfit_plan(person, plan, tryon.LocalCodexImageGenTryOnProvider())
    assert result['status'] == 'failed'
    assert result['decision']['user_message'] == '这次试穿生成超时，请稍后重试。'
    assert result['pipeline']['quality_review']['evidence']['reason'] == 'image_generation_failed'

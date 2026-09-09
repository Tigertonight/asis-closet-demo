import json
from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException
from PIL import Image

from app import local_codex, selfit_outfit_match as matching


@pytest.fixture(autouse=True)
def local_runtime(monkeypatch):
    monkeypatch.setenv('SELFIT_ENV', 'local')
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', '0')
    monkeypatch.delenv('SELFIT_CODEX_MODEL', raising=False)
    monkeypatch.setattr(local_codex, '_binary', lambda: '/test/codex')


def test_local_provider_preserves_image_schema_and_isolates_execution(monkeypatch):
    calls = []
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            calls.append((command, kwargs))
            self.command = command
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, prompt, timeout):
            assert '只分析已附图片' in prompt and 'wardrobe input' in prompt
            assert timeout == 120
            command = self.command
            image = Path(command[command.index('--image') + 1])
            assert Image.open(image).getpixel((0, 0)) == (12, 34, 56)
            schema = Path(command[command.index('--output-schema') + 1])
            assert json.loads(schema.read_text()) == matching.ANALYSIS_SCHEMA
            Path(command[command.index('--output-last-message') + 1]).write_text('{"slot":"top","description":"上衣"}')
    monkeypatch.setattr(local_codex.subprocess, 'Popen', Process)
    monkeypatch.setenv('SELFIT_OUTFIT_MATCH_PROVIDER', 'codex')
    result = matching.ask_vision(Image.new('RGB', (2, 2), (12, 34, 56)), 'wardrobe input', matching.ANALYSIS_SCHEMA)
    assert result['slot'] == 'top'
    command, options = calls[0]
    assert command[-1] == '-' and '--model' not in command
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert command[command.index('--ask-for-approval') + 1] == 'never'
    assert all(flag in command for flag in ['--ephemeral', '--ignore-user-config', 'shell_tool', 'apps', 'plugins'])
    assert not options.get('shell') and options['start_new_session']
    assert not options['cwd'].exists()  # All request artifacts are deleted.


@pytest.mark.parametrize('mode,public', [('production','0'), ('demo','0'), ('staging','0'), ('local','1')])
def test_codex_cannot_use_developer_login_in_public_deployment(monkeypatch, mode, public):
    monkeypatch.setenv('SELFIT_ENV', mode)
    monkeypatch.setenv('SELFIT_PUBLIC_DEMO', public)
    monkeypatch.setattr(local_codex.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not spawn'))
    with pytest.raises(HTTPException) as error:
        local_codex.ask_json(Image.new('RGB',(1,1)), 'prompt', matching.ANALYSIS_SCHEMA)
    assert error.value.status_code == 503


@pytest.mark.parametrize('failure,status', [('exit',503), ('timeout',504), ('invalid',502)])
def test_failures_release_lock_clean_files_and_do_not_expose_cli_output(monkeypatch, failure, status):
    paths, killed = [], []
    class Process:
        pid = 12345
        returncode = 1 if failure == 'exit' else 0
        def __init__(self, command, **kwargs):
            self.command = command
            paths.append(kwargs['cwd'])
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, *args, **kwargs):
            if failure == 'timeout' and kwargs.get('timeout'):
                raise subprocess.TimeoutExpired('secret CLI output', 120)
            if failure == 'invalid':
                Path(self.command[self.command.index('--output-last-message')+1]).write_text('secret invalid output')
    monkeypatch.setattr(local_codex.subprocess, 'Popen', Process)
    monkeypatch.setattr(local_codex.os, 'killpg', lambda *args: killed.append(args))
    with pytest.raises(HTTPException) as error:
        local_codex.ask_json(Image.new('RGB',(1,1)), 'prompt', matching.ANALYSIS_SCHEMA)
    assert error.value.status_code == status and 'secret' not in error.value.detail
    assert not paths[0].exists()
    assert bool(killed) == (failure == 'timeout')
    assert local_codex._CALL_LOCK.acquire(blocking=False)
    local_codex._CALL_LOCK.release()


def test_busy_request_does_not_start_another_cli(monkeypatch):
    monkeypatch.setattr(local_codex.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not spawn'))
    local_codex._CALL_LOCK.acquire()
    try:
        with pytest.raises(HTTPException) as error:
            local_codex.ask_json(Image.new('RGB',(1,1)), 'prompt', matching.ANALYSIS_SCHEMA)
        assert error.value.status_code == 429
    finally:
        local_codex._CALL_LOCK.release()

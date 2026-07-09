from __future__ import annotations

from pathlib import Path

from scripts.pi_agent_tryon_worker import ROOT_DIR, build_pi_command, build_worker_prompt


def test_pi_worker_command_passes_mask_as_third_image() -> None:
    prompt = "Generate a try-on image."

    command = build_pi_command(
        "openai-codex",
        "gpt-test",
        ROOT_DIR / "uploads" / "person.png",
        ROOT_DIR / "uploads" / "garment.png",
        ROOT_DIR / "outputs" / "tryon" / "case" / "mask.png",
        prompt,
    )

    assert command[:7] == ["pi", "--provider", "openai-codex", "--model", "gpt-test", "--no-session", "-p"]
    assert command[7] == f"@{ROOT_DIR / 'uploads' / 'person.png'}"
    assert command[8] == f"@{ROOT_DIR / 'uploads' / 'garment.png'}"
    assert command[9] == f"@{ROOT_DIR / 'outputs' / 'tryon' / 'case' / 'mask.png'}"
    assert command[10] == prompt


def test_pi_worker_prompt_describes_three_inputs_and_mask_contract() -> None:
    job = {"prompt": "Original provider prompt: keep face and background unchanged."}

    prompt = build_worker_prompt(job, "result.png")

    assert "three inputs" in prompt
    assert "Image C is the edit mask" in prompt
    assert "black or transparent pixels" in prompt
    assert "white or opaque pixels are protected" in prompt
    assert "two images" not in prompt
    assert "Original provider prompt" in prompt


def test_pi_worker_root_stays_inside_current_project() -> None:
    assert ROOT_DIR == Path(__file__).resolve().parents[1]
    assert "aicopilot" not in str(ROOT_DIR)

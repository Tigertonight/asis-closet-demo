from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_closing_save_guide_returns_to_selected_share_card() -> None:
    runtime = (ROOT / "app/static/selfit/selfit.js").read_text(encoding="utf-8")

    assert "const resetSaveImageGuide = () =>" in runtime
    assert "resetSaveImageGuide();\n    openShareDialog();" in runtime
    assert "goToShareSlide(shareSlideIndex, false);" in runtime
    assert "shareSaveButton.focus({ preventScroll: true });" not in runtime
    assert "if (event.key !== 'Escape') return;" in runtime

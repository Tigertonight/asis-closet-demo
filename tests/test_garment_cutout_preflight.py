from PIL import Image
import pytest

from scripts.prepare_selfit_garment_asset import prepare


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_opaque_source_cannot_pass_by_adding_canvas_padding(tmp_path, mode):
    source, target = tmp_path / "opaque.png", tmp_path / "prepared.png"
    Image.new(mode, (40, 60), "white").save(source)
    with pytest.raises(ValueError, match="background extraction is required"):
        prepare(source, target)
    assert not target.exists()


def test_actual_transparent_cutout_is_normalized_without_losing_subject(tmp_path):
    source, target = tmp_path / "cutout.png", tmp_path / "prepared.png"
    image = Image.new("RGBA", (40, 60), (0, 0, 0, 0))
    image.paste((120, 90, 60, 255), (10, 10, 30, 50))
    image.save(source)
    result = prepare(source, target, size=120)
    assert result["passed"] is True
    assert result["transparent_ratio"] > .4
    assert min(result["margins"].values()) >= .09
    with Image.open(target) as output:
        assert output.getpixel((0, 0))[3] == 0
        assert output.getpixel((60, 60)) == (120, 90, 60, 255)


def test_fully_transparent_input_has_no_garment(tmp_path):
    source, target = tmp_path / "empty.png", tmp_path / "prepared.png"
    Image.new("RGBA", (40, 60), (0, 0, 0, 0)).save(source)
    with pytest.raises(ValueError, match="no meaningful"):
        prepare(source, target)
    assert not target.exists()

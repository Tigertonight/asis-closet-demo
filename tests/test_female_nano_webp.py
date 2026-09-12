from PIL import Image
import pytest

from scripts.convert_female_nano_presets_webp import convert


def test_lossless_conversion_preserves_transparent_colors_and_detects_changed_file(tmp_path):
    source = tmp_path / 'source.png'
    target = tmp_path / 'display.webp'
    im = Image.new('RGBA', (32, 48))
    im.putdata([(x * 7 % 256, x * 13 % 256, x * 17 % 256, x % 256) for x in range(32 * 48)])
    im.save(source)
    original_bytes = source.read_bytes()
    assert convert(source, target) == [32, 48]
    assert source.read_bytes() == original_bytes
    assert convert(source, target) == [32, 48]
    Image.new('RGB', (32, 48), 'white').save(target, 'WEBP', lossless=True)
    with pytest.raises(AssertionError, match='pixels changed'):
        convert(source, target)

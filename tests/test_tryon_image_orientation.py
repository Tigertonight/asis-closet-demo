import io

import numpy as np
import pytest
from PIL import Image, ImageOps

from app import tryon


@pytest.mark.parametrize('orientation', range(1, 9))
def test_orientation_matches_provider_pixels_and_survives_job_reread(tmp_path, monkeypatch, orientation):
    monkeypatch.setattr(tryon, '_upload_dir', lambda: tmp_path)
    pixels = np.arange(48 * 32 * 3, dtype=np.uint8).reshape(32, 48, 3)
    source = Image.fromarray(pixels)
    exif = Image.Exif()
    exif[274] = orientation
    buffer = io.BytesIO()
    source.save(buffer, 'PNG', exif=exif)
    raw = buffer.getvalue()
    expected = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    upload = tryon._read_upload_image(raw, 'phone.png', 'person')
    provider_image = Image.open(upload['saved_path'])
    assert np.array_equal(np.asarray(upload['image']), np.asarray(expected))
    assert np.array_equal(np.asarray(provider_image), np.asarray(expected))
    assert provider_image.getexif().get(274, 1) == 1
    reread = tryon._read_upload_image(upload['saved_path'].read_bytes(), 'phone.png', 'person')
    assert reread['image_id'] == upload['image_id']
    assert np.array_equal(np.asarray(reread['image']), np.asarray(expected))
    assert (upload['meta']['width'], upload['meta']['height']) == expected.size

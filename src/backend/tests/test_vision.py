import io

import numpy as np
import pytest
from PIL import Image

import generate_demo_images as gen
from clearpath import vision


def test_smooth_sidewalk_has_no_damage():
    rng = np.random.default_rng(100)
    analysis, _ = vision.analyze(gen.generate("no visible damage", rng))
    assert analysis.level == "no visible damage"


def test_sidewalk_with_cracks_and_pothole_is_severe():
    rng = np.random.default_rng(101)
    analysis, overlay = vision.analyze(gen.generate("severe", rng))
    assert analysis.level == "severe"
    assert analysis.pothole_pct > 0 and analysis.crack_pct > 0
    assert overlay.shape[1] == vision.WIDTH


def test_straight_paving_joints_do_not_count_as_cracks():
    img = gen.concrete_texture(np.random.default_rng(5))
    gen.joints(img, np.random.default_rng(6))
    analysis, _ = vision.analyze(img)
    assert analysis.joints_removed > 0
    assert analysis.level == "no visible damage"


def test_removes_exif_metadata():
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    Image.new("RGB", (64, 64), (150, 150, 150)).save(buf, "JPEG", exif=exif)
    assert Image.open(io.BytesIO(buf.getvalue())).getexif().get(0x010F) == "PhoneMaker"

    clean = vision.reencode_without_metadata(vision.decode(buf.getvalue()))
    assert len(Image.open(io.BytesIO(clean)).getexif()) == 0


def test_invalid_file():
    with pytest.raises(ValueError):
        vision.decode(b"this is not an image")

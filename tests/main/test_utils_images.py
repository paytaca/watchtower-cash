"""Tests for the untrusted-image helpers (Pillow CVE mitigation)."""
from io import BytesIO

import pytest
from PIL import Image

from main.utils.images import (
    ALLOWED_IMAGE_FORMATS,
    UnsupportedImageFormat,
    fit_within,
    open_image,
)


def image_bytes(fmt="PNG", size=(100, 50), color="red"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def test_allowed_formats_are_lowercase_plugin_names():
    # Pillow reports uppercase plugin names, and Image.format is compared
    # against this set directly.
    assert {"BMP", "GIF", "ICO", "JPEG", "PNG", "WEBP"} == ALLOWED_IMAGE_FORMATS


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_open_image_accepts_supported_formats(fmt):
    image = open_image(image_bytes(fmt))
    assert image.format == fmt


def test_open_image_rejects_tiff():
    with pytest.raises(UnsupportedImageFormat, match="TIFF"):
        open_image(image_bytes("TIFF"))


def test_open_image_rejects_eps():
    # Minimal EPS header; open_image rejects it at the format check without
    # ever loading/decoding it (which would invoke Ghostscript).
    eps = BytesIO(b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n")
    with pytest.raises(UnsupportedImageFormat, match="EPS"):
        open_image(eps)


def test_fit_within_never_calls_draft(monkeypatch):
    # Image.thumbnail() uses draft() for JPEGs; fit_within must not.
    def fail_draft(*args, **kwargs):
        raise AssertionError("Image.draft() must not be called")

    monkeypatch.setattr(Image.Image, "draft", fail_draft)

    image = Image.open(image_bytes("JPEG", size=(800, 400)))
    resized = fit_within(image, (100, 100))
    assert resized.size == (100, 50)


def test_fit_within_preserves_aspect_ratio():
    image = Image.new("RGB", (800, 400))
    resized = fit_within(image, (450, 450))
    assert resized.size == (450, 225)


def test_fit_within_leaves_smaller_images_unchanged():
    image = Image.new("RGB", (50, 25))
    resized = fit_within(image, (200, 200))
    assert resized.size == (50, 25)


def test_fit_within_accepts_size_with_computed_height():
    image = Image.new("RGB", (900, 300))
    resized = fit_within(image, (450, 150))
    assert resized.size == (450, 150)

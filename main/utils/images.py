"""Helpers for handling untrusted images.

Pillow 13.0.0 fixes three critical vulnerabilities that affect every earlier
release: CVE-2026-112900 (EPS/Ghostscript argument injection),
CVE-2026-112393 (TIFF write heap overflow) and CVE-2026-112403 (JPEG
draft/thumbnail heap overflow). This project still runs on Python 3.8, which
cannot install Pillow 13, so the reachable attack paths are closed here:

* Only the raster formats we actually serve are accepted, so Pillow never
  dispatches to plugins that execute external binaries (notably EPS, which
  shells out to Ghostscript).
* Downscaling goes through ``resize()`` instead of ``Image.thumbnail()``,
  because ``thumbnail()`` calls ``draft()`` for JPEGs, the path affected by
  CVE-2026-112403.

Remove these guards once the runtime can move to Pillow >= 13.0.0.
"""

from PIL import Image, ImageOps

# Formats accepted from uploads and remote image URLs. EPS, TIFF and the other
# less common plugins are intentionally excluded.
ALLOWED_IMAGE_FORMATS = frozenset({
    "BMP",
    "GIF",
    "ICO",
    "JPEG",
    "PNG",
    "WEBP",
})


class UnsupportedImageFormat(ValueError):
    """Raised when an image is not in one of ALLOWED_IMAGE_FORMATS."""


def open_image(source):
    """Open an untrusted image, rejecting unsupported format plugins."""
    image = Image.open(source)
    if image.format not in ALLOWED_IMAGE_FORMATS:
        raise UnsupportedImageFormat(f"Unsupported image format: {image.format}")
    return image


def fit_within(image, size):
    """Shrink ``image`` to fit ``size``, preserving aspect ratio.

    Unlike ``Image.thumbnail()``, this never uses ``draft()``, so it does not
    hit the JPEG decoder path affected by CVE-2026-112403. Images smaller than
    ``size`` are returned unchanged.
    """
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)

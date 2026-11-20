import os
import hashlib
from urllib.parse import urljoin
from pathlib import Path
from tempfile import NamedTemporaryFile
from PIL import Image
from io import BytesIO 

from main.utils.images import fit_within

from django.conf import settings
from rampp2p import models
from rampp2p.proof_storage import bounded_path, private_proof_root, legacy_proof_root, proof_relative_path

import logging
logger = logging.getLogger(__name__)

def save_image(img: Image, max_width=None, request=None, path=None):
    # NOTE: use `path` param with caution, consider checking the OS running this code
    width, height = img.size
    if max_width and width > max_width:
        new_width = max_width
        new_height = int((new_width / width) * height)
        new_size = (new_width, new_height)
        img = fit_within(img, new_size)

    file_hash = get_image_file_hash(img)
    file_ext = (img.format or "png").lower()
    file_name = f"{file_hash}.{file_ext}"
    relative = Path(path or '') / file_name
    root = private_proof_root()
    file_path = bounded_path(root, relative)
    file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=file_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            img.save(temporary, format=img.format or 'PNG')
        os.replace(temporary_path, file_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    url = None
    url_path = urljoin(settings.IMAGE_UPLOAD_PATH + "/", file_name)
    if path:
        _url_path = urljoin(settings.IMAGE_UPLOAD_PATH + "/", path)
        if not _url_path.endswith("/"): _url_path += "/"
        url_path = urljoin(_url_path, file_name)

    if request:
        protocol = "https" if request.is_secure() else "http"
        url = urljoin(f"{protocol}://{request.get_host()}", url_path)

    instance, _ = models.ImageUpload.objects.update_or_create(
        file_hash=file_hash, defaults={'url': url, 'url_path': url_path},
    )
    return instance

def delete_file(path):
    relative = proof_relative_path(path)
    for root in (private_proof_root(), legacy_proof_root()):
        target = bounded_path(root, relative)
        if target.is_file():
            target.unlink()

def get_image_file_hash(img):
    byte_data = BytesIO()
    img.save(byte_data, 'PNG')
    return get_bytes_hash(byte_data)

def get_bytes_hash(bytes_io_obj:BytesIO):
    sha256 = hashlib.sha256()
    sha256.update(bytes_io_obj.getvalue())
    file_hash = sha256.hexdigest()
    return file_hash

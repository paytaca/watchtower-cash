import os
import hashlib
from requests.compat import urljoin
from PIL import Image
from io import BytesIO 

from django.conf import settings
from rampp2p import models

import logging
logger = logging.getLogger(__name__)

def save_image(img: Image, max_width=None, request=None, path=None):
    # NOTE: use `path` param with caution, consider checking the OS running this code
    width, height = img.size
    if max_width and width > max_width:
        new_width = max_width
        new_height = int((new_width / width) * height)
        new_size = (new_width, new_height)
        img = img.resize(new_size, Image.ANTIALIAS)

    file_hash = get_image_file_hash(img)
    file_ext = (img.format or "png").lower()
    file_name = f"{file_hash}.{file_ext}"
    file_path = os.path.join(settings.IMAGE_UPLOAD_ROOT, file_name)
    file_dir = settings.IMAGE_UPLOAD_ROOT
    if path:
        file_path = os.path.join(settings.IMAGE_UPLOAD_ROOT, path, file_name)
        file_dir = os.path.join(settings.IMAGE_UPLOAD_ROOT, path)

    if not os.path.exists(file_dir): os.makedirs(file_dir)
    
    img.save(file_path)

    url = None
    url_path = urljoin(settings.IMAGE_UPLOAD_PATH + "/", file_name)
    if path:
        _url_path = urljoin(settings.IMAGE_UPLOAD_PATH + "/", path)
        if not _url_path.endswith("/"): _url_path += "/"
        url_path = urljoin(_url_path, file_name)

    if request:
        protocol = "https" if request.is_secure() else "http"
        url = urljoin(f"{protocol}://{request.get_host()}", url_path)

    instance, _ = models.ImageUpload.objects.update_or_create(url=url, file_hash=file_hash, url_path=url_path)
    return instance

def delete_file(path):
    path = f'.{path}'
    if path and os.path.exists(path):
        os.remove(path)
        logger.warn(f'Successfully deleted {path}.')
    else:
        logger.warn(f'File {path} not found.')

def get_image_file_hash(img):
    byte_data = BytesIO()
    img.save(byte_data, 'PNG')
    return get_bytes_hash(byte_data)

def get_bytes_hash(bytes_io_obj:BytesIO):
    sha256 = hashlib.sha256()
    sha256.update(bytes_io_obj.getvalue())
    file_hash = sha256.hexdigest()
    return file_hash

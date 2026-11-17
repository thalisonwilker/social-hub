import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def make_image_bytes(fmt="JPEG", size=(40, 20), mode="RGB", color=(200, 30, 30), exif=None):
    image = Image.new(mode, size, color if mode in ("RGB", "RGBA") else 0)
    buf = io.BytesIO()
    kwargs = {}
    if exif is not None:
        kwargs["exif"] = exif
    image.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def make_upload(name="foto.jpg", content_type="image/jpeg", **kwargs):
    return SimpleUploadedFile(name, make_image_bytes(**kwargs), content_type=content_type)

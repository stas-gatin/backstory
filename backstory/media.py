"""Checks and normalises uploads before anything is spent on them."""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

try:  # HEIC/HEIF photos from phones
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # no wheel for this Python; fall back to macOS sips below
    pillow_heif = None

MAX_SIDE = 2048


class BadMedia(Exception):
    pass


def _open(data):
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        return im
    except Exception:  # noqa: BLE001 - try the fallback, then report
        pass
    if shutil.which("sips"):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in", Path(tmp) / "out.jpg"
            src.write_bytes(data)
            p = subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)], capture_output=True,
                               timeout=60)
            if p.returncode == 0 and dst.exists():
                im = Image.open(io.BytesIO(dst.read_bytes()))
                im.load()
                return im
    raise BadMedia("this file is not a photo Backstory can read (use JPEG, PNG, WebP or HEIC)")


def normalise_image(data):
    """JPEG bytes, upright (EXIF rotation applied), at most MAX_SIDE pixels on the long side."""
    im = ImageOps.exif_transpose(_open(data)).convert("RGB")
    if im.width < 32 or im.height < 32:
        raise BadMedia("the image is too small to search for")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

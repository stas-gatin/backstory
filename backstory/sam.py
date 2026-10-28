"""Photo cut-out with SAM 3.1: find the photo inside a screenshot of a post, so that reverse image search gets the
photo and not the account name, text and buttons around it."""
import base64
import io
import json
import re

from PIL import Image

from . import config, meta, replay

SAM = "sam-3.1"
PRICE_PER_IMAGE = 2.5 / 1000
BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([0-9.]+))?\|>")


def boxes(image_bytes, phrase="photo", budget=None):
    """Boxes [(x1, y1, x2, y2, confidence)] in pixels of the given image, best first."""
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    body = {"model": SAM, "stream": False,
            "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": phrase},
                {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}]}]}
    if budget:
        budget.check()
    j = replay.cached("sam", body, lambda: meta._post(body), note="sam " + phrase)
    if budget:
        budget.add_usd(SAM, PRICE_PER_IMAGE)
    out = []
    for m in BOX.finditer(meta.output_text(j) or json.dumps(j)):
        x1, y1, x2, y2, w, h = (int(m.group(i)) for i in range(1, 7))
        sx, sy = im.width / w, im.height / h
        out.append((x1 * sx, y1 * sy, x2 * sx, y2 * sy, float(m.group(7) or 0)))
    return sorted(out, key=lambda b: -b[4])


def _inside(a, b, share=0.9):
    """True when at least `share` of box a lies inside box b."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1])
    return area > 0 and ix * iy / area >= share


def photo_regions(image_bytes, budget=None, min_share=0.06, max_regions=3, min_conf=0.5):
    """Separate photos inside a post screenshot or collage, as JPEG crops (largest first).

    Keeps confident 'photo' boxes that are not tiny and not nested inside a larger kept box (a framed picture
    inside a scene is part of that scene). Returns [] when the image is a single photo already."""
    found = [b for b in boxes(image_bytes, budget=budget) if b[4] >= min_conf]
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    total = im.width * im.height
    kept = []
    for b in sorted(found, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        share = (b[2] - b[0]) * (b[3] - b[1]) / total
        if share < min_share or any(_inside(b, k) for k in kept):
            continue
        kept.append(b)
    if len(kept) == 1 and (kept[0][2] - kept[0][0]) * (kept[0][3] - kept[0][1]) / total > 0.9:
        return []
    out = []
    for x1, y1, x2, y2, c in kept[:max_regions]:
        buf = io.BytesIO()
        im.crop((int(x1), int(y1), int(x2), int(y2))).save(buf, format="JPEG", quality=92)
        out.append({"box": (x1, y1, x2, y2), "conf": c, "jpeg": buf.getvalue()})
    return out

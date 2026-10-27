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


def cut_out(image_bytes, budget=None, min_share=0.08):
    """(photo bytes, box) for the most confident 'photo' box, or (original bytes, None) when there is none or the
    box covers almost the whole image anyway."""
    found = boxes(image_bytes, budget=budget)
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    for x1, y1, x2, y2, c in found:
        share = (x2 - x1) * (y2 - y1) / (im.width * im.height)
        if share < min_share:
            continue
        if share > 0.97:
            return image_bytes, None
        buf = io.BytesIO()
        im.crop((int(x1), int(y1), int(x2), int(y2))).save(buf, format="JPEG", quality=92)
        return buf.getvalue(), (x1, y1, x2, y2, c)
    return image_bytes, None

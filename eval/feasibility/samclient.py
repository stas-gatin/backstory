"""Minimal SAM 3.1 client: one image + one noun phrase -> boxes (and raw mask tokens)."""
import base64
import io
import json
import os
import re
import time

import requests

API = "https://api.meta.ai/v1/responses"


def load_key():
    key = os.environ.get("MODEL_API_KEY")
    if key:
        return key
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, ".env")) as f:
        for line in f:
            if line.startswith("MODEL_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("MODEL_API_KEY not set")


def segment(pil_image, phrase, include_confidence=True, retries=3):
    """Returns (raw_response_json, output_text)."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    body = {
        "model": "sam-3.1",
        "input": [{
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": phrase},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
        "stream": False,
        "metadata": {"mask_encoding": "one_bit",
                     "include_confidence": "true" if include_confidence else "false"},
    }
    headers = {"Authorization": "Bearer " + load_key(), "Content-Type": "application/json"}
    last = None
    for attempt in range(retries):
        r = requests.post(API, headers=headers, data=json.dumps(body), timeout=120)
        if r.status_code == 200:
            j = r.json()
            return j, extract_text(j)
        last = (r.status_code, r.text[:300])
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("SAM call failed: %s" % (last,))


def extract_text(j):
    """Pull the segmentation text out of a Responses API JSON."""
    if isinstance(j.get("output_text"), str):
        return j["output_text"]
    parts = []
    for item in j.get("output", []):
        for c in item.get("content", []) or []:
            if isinstance(c, dict) and "text" in c:
                parts.append(c["text"])
    return "".join(parts)


BOX_RE = re.compile(
    r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([0-9.]+))?\|>")


def parse_boxes(text):
    out = []
    for m in BOX_RE.finditer(text or ""):
        x1, y1, x2, y2, w, h = (int(m.group(i)) for i in range(1, 7))
        c = float(m.group(7)) if m.group(7) else None
        out.append({"box": (x1, y1, x2, y2), "size": (w, h), "conf": c})
    return out

"""Agent: the match checker (Muse Spark, sees two images).

Image search returns exact matches and "visually similar" images. Similar is not the same: many floods look alike.
For posts with no exact match (typical for video frames, crops and re-encodes), this agent compares each candidate
with the post's image and keeps only those that show the same moment from the same footage or photo.
"""
import io

import requests
from PIL import Image

from . import config, meta, replay

UA = {"User-Agent": "Mozilla/5.0 (compatible; Backstory/0.1; photo provenance research)"}
MAX_BYTES = 6_000_000

PROMPT = """Image 1 is from a social media post. Image 2 was found online by a visual similarity search.

Do they come from the SAME original photo or video footage (same moment, same camera position, same objects in
the same places; image 2 may be cropped, resized, recoloured, a nearby frame of the same video, or carry text)?
A similar scene of the same kind (another flood, another crowd, another angle) is NOT the same.

Reply with one JSON object:
{"same": true | false, "confidence": "high" | "medium" | "low", "reason": "one short sentence naming what matches or differs"}
Answer "same": true only with high confidence."""


def download(url):
    def fetch():
        try:
            r = requests.get(url, headers=UA, timeout=20, stream=True)
            data = r.raw.read(MAX_BYTES + 1, decode_content=True)
            if r.status_code != 200 or len(data) > MAX_BYTES:
                return {"ok": False}
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((1024, 1024))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88)
            return {"ok": True, "jpeg_hex": buf.getvalue().hex()}
        except Exception:  # noqa: BLE001 - an unreadable candidate is simply skipped
            return {"ok": False}
    res = replay.cached("candidate", {"url": url}, fetch, note=url[:200])
    return bytes.fromhex(res["jpeg_hex"]) if res.get("ok") else None


def same_source(post_image, url, budget=None):
    """{'url', 'same', 'confidence', 'reason'}; same is False when the candidate cannot be downloaded."""
    cand = download(url)
    if cand is None:
        return {"url": url, "same": False, "reason": "could not download"}
    try:
        out, _ = meta.ask_json(config.SPARK, PROMPT, images=[post_image, cand], budget=budget,
                               note="match " + url[:150])
    except ValueError:
        return {"url": url, "same": False, "reason": "no answer"}
    out["same"] = bool(out.get("same")) and out.get("confidence") == "high"
    out["url"] = url
    return out

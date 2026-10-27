"""Reverse image search: where else on the web does this exact photo appear?

The live provider is Google Cloud Vision Web Detection (Meta's API has no image search). Each match is a page
plus the URLs of the matching image files on it.
"""
import base64
import hashlib
import io
import re
from urllib.parse import urlparse

import requests
from PIL import Image

from . import config, replay

FACT_CHECKERS = """maldita.es newtral.es efe.com verificat.cat factly.in pesacheck.org africacheck.org afp.com
boomlive.in altnews.in newschecker.in thequint.com vishvasnews.com snopes.com reuters.com factcheck.org
politifact.com fullfact.org leadstories.com checkyourfact.com logicallyfacts.com misbar.com dubawa.org faktisk.no haqcheck.org ethiopiacheck.org""".split()


def domain(url):
    u = urlparse(url)
    host = u.netloc.lower()
    first = u.path.split("/")[1] if u.path.count("/") > 1 else ""
    # Image CDNs that put the real site in the path (i0.wp.com/example.org/...).
    if re.fullmatch(r"i\d\.wp\.com", host) and "." in first:
        host = first.lower()
    return host[4:] if host.startswith("www.") else host


def is_fact_checker(url):
    host = domain(url)
    return any(host == d or host.endswith("." + d) for d in FACT_CHECKERS)


# URLs that look like a fact-check or debunk of the photo itself (used when fact-checkers are excluded in tests).
DEBUNK_URL = re.compile(r"fact-?check|fake|hoax|misleading|false|debunk|verif", re.I)


def looks_like_debunk(url):
    return is_fact_checker(url) or bool(DEBUNK_URL.search(url))


LOW_VALUE = """youtube.com yelp.com pinterest.com facebook.com instagram.com x.com twitter.com tiktok.com
reddit.com threads.net linkedin.com""".split()


def low_value(url):
    host = domain(url)
    return any(host == d or host.endswith("." + d) or host.split(".")[-2:-1] == [d.split(".")[0]]
               for d in LOW_VALUE)


class SearchUnavailable(Exception):
    pass


def _fit(image_bytes, limit=4_000_000):
    """Re-encode images too large for one Vision request (10 MB including base64)."""
    if len(image_bytes) <= limit:
        return image_bytes
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    im.thumbnail((2048, 2048))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def google_vision(image_bytes):
    """Pages with a full or partial match of the image, best matches first."""
    sha = hashlib.sha256(image_bytes).hexdigest()

    def fetch():
        if not config.GOOGLE_VISION_API_KEY:
            raise SearchUnavailable("reverse image search needs GOOGLE_VISION_API_KEY")
        body = {"requests": [{"image": {"content": base64.b64encode(_fit(image_bytes)).decode()},
                              "features": [{"type": "WEB_DETECTION", "maxResults": 50}]}]}
        try:
            r = requests.post("https://vision.googleapis.com/v1/images:annotate",
                              params={"key": config.GOOGLE_VISION_API_KEY}, json=body, timeout=60)
        except requests.RequestException as e:
            raise SearchUnavailable("image search did not answer (%s)" % type(e).__name__)
        if r.status_code != 200:
            raise SearchUnavailable("image search failed (HTTP %d)" % r.status_code)
        answer = r.json()["responses"][0]
        if "error" in answer:  # never recorded: it would turn into a false "no copies online"
            raise SearchUnavailable("image search failed: %s" % answer["error"].get("message", "unknown error"))
        return answer.get("webDetection", {})

    web = replay.cached("vision", {"image_sha256": sha}, fetch, note="web detection")
    pages = []
    for p in web.get("pagesWithMatchingImages", []):
        full = [i["url"] for i in p.get("fullMatchingImages", [])]
        partial = [i["url"] for i in p.get("partialMatchingImages", [])]
        pages.append({"url": p["url"], "title": p.get("pageTitle", ""), "image_urls": full + partial,
                      "match": "full" if full else "partial"})
    pages.sort(key=lambda p: p["match"] != "full")
    return {"pages": pages, "best_guess": [l.get("label") for l in web.get("bestGuessLabels", [])],
            "similar": [i["url"] for i in web.get("visuallySimilarImages", [])]}


def from_list(pages):
    """Use a fixed list of matches (evaluation on a dataset whose search results were recorded earlier)."""
    return {"pages": pages, "best_guess": [], "similar": []}

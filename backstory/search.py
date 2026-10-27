"""Reverse image search: where else on the web does this exact photo appear?

The live provider is Google Cloud Vision Web Detection (Meta's API has no image search). Each match is a page
plus the URLs of the matching image files on it.
"""
import base64
import hashlib
from urllib.parse import urlparse

import requests

from . import config, replay

FACT_CHECKERS = """maldita.es newtral.es efe.com verificat.cat factly.in pesacheck.org africacheck.org afp.com
boomlive.in altnews.in newschecker.in thequint.com vishvasnews.com snopes.com reuters.com factcheck.org
politifact.com fullfact.org logicallyfacts.com misbar.com dubawa.org faktisk.no haqcheck.org ethiopiacheck.org""".split()


def domain(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_fact_checker(url):
    host = domain(url)
    return any(host == d or host.endswith("." + d) for d in FACT_CHECKERS)


class SearchUnavailable(Exception):
    pass


def google_vision(image_bytes):
    """Pages with a full or partial match of the image, best matches first."""
    sha = hashlib.sha256(image_bytes).hexdigest()

    def fetch():
        if not config.GOOGLE_VISION_API_KEY:
            raise SearchUnavailable("reverse image search needs GOOGLE_VISION_API_KEY")
        body = {"requests": [{"image": {"content": base64.b64encode(image_bytes).decode()},
                              "features": [{"type": "WEB_DETECTION", "maxResults": 50}]}]}
        r = requests.post("https://vision.googleapis.com/v1/images:annotate",
                          params={"key": config.GOOGLE_VISION_API_KEY}, json=body, timeout=60)
        r.raise_for_status()
        return r.json()["responses"][0].get("webDetection", {})

    web = replay.cached("vision", {"image_sha256": sha}, fetch, note="web detection")
    pages = []
    for p in web.get("pagesWithMatchingImages", []):
        full = [i["url"] for i in p.get("fullMatchingImages", [])]
        partial = [i["url"] for i in p.get("partialMatchingImages", [])]
        pages.append({"url": p["url"], "title": p.get("pageTitle", ""), "image_urls": full + partial,
                      "match": "full" if full else "partial"})
    pages.sort(key=lambda p: p["match"] != "full")
    return {"pages": pages, "best_guess": [l.get("label") for l in web.get("bestGuessLabels", [])]}


def from_list(pages):
    """Use a fixed list of matches (evaluation on a dataset whose search results were recorded earlier)."""
    return {"pages": pages, "best_guess": []}

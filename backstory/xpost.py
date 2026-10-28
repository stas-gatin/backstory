"""Read a post on X from its link: text, publication date, photos or video.

Uses the public data X serves for embedded posts (no account, no API key). The post's Community Note, if any, is
kept apart: it is shown next to Backstory's verdict for comparison and never given to the agents.
"""
import math
import re

import requests

from . import replay

LINK = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d+)", re.I)
UA = {"User-Agent": "Mozilla/5.0 (compatible; Backstory/0.1)"}
MAX_VIDEO_BYTES = 60_000_000


class PostError(Exception):
    pass


def post_id(url):
    m = LINK.search(url or "")
    if not m:
        raise PostError("not a link to a post on X (expected x.com/<user>/status/<number>)")
    return m.group(1)


def _token(pid):
    # The embed endpoint expects this token derived from the post id.
    n = (int(pid) / 1e15) * math.pi
    digits, whole, frac = "0123456789abcdefghijklmnopqrstuvwxyz", int(n), n - int(n)
    out = ""
    while whole:
        out = digits[whole % 36] + out
        whole //= 36
    out = (out or "0") + "."
    for _ in range(12):
        frac *= 36
        out += digits[int(frac)]
        frac -= int(frac)
    return re.sub(r"(0+|\.)", "", out)


def _fetch_json(pid):
    r = requests.get("https://cdn.syndication.twimg.com/tweet-result",
                     params={"id": pid, "token": _token(pid), "lang": "en"}, headers=UA, timeout=20)
    if r.status_code in (400, 404) or not r.text.strip():
        return {"missing": True}
    if r.status_code != 200:
        raise PostError("X did not answer (HTTP %d); try again later" % r.status_code)
    return r.json()


def _download(url, limit):
    def fetch():
        r = requests.get(url, headers=UA, timeout=60, stream=True)
        if r.status_code != 200:
            return None
        data = r.raw.read(limit + 1, decode_content=True)
        return data if len(data) <= limit else None
    return replay.cached_bytes("xmedia", {"url": url}, fetch)


def read(url):
    """{'id', 'url', 'author', 'text', 'posted_on', 'photos': [bytes], 'video': bytes or None,
        'has_media': bool, 'community_note': str or None}"""
    pid = post_id(url)
    # A "missing" answer is not recorded: it may be a passing error, and a deleted post costs nothing to ask again.
    j = replay.cached("xpost", {"id": pid}, lambda: _fetch_json(pid), note="x post " + pid,
                      keep=lambda r: not r.get("missing"))
    if j.get("missing") or j.get("__typename") == "TweetTombstone":
        raise PostError("the post is deleted, private or age-restricted")
    start, end = (j.get("display_text_range") or [0, len(j.get("text", ""))])[:2]
    text = re.sub(r"\s*https://t\.co/\S+", "", j.get("text", "")[start:end]).strip()
    photos, video = [], None
    for m in j.get("mediaDetails", []):
        if m.get("type") == "photo":
            data = _download(m["media_url_https"] + "?name=large", 15_000_000)
            if data:
                photos.append(data)
        elif m.get("type") in ("video", "animated_gif") and video is None:
            mp4 = [v for v in m.get("video_info", {}).get("variants", []) if v.get("content_type") == "video/mp4"]
            if mp4:
                best = max(mp4, key=lambda v: v.get("bitrate") or 0)
                video = _download(best["url"], MAX_VIDEO_BYTES)
    note = ((j.get("birdwatch_pivot") or {}).get("subtitle") or {}).get("text")
    return {"id": pid, "url": "https://x.com/%s/status/%s" % ((j.get("user") or {}).get("screen_name", "i"), pid),
            "author": (j.get("user") or {}).get("screen_name"), "text": text,
            "posted_on": (j.get("created_at") or "")[:10] or None,
            "photos": photos, "video": video, "has_media": bool(j.get("mediaDetails")), "community_note": note}

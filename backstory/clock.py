"""Post clock (code, no model): exact posting dates of copies on X, TikTok and YouTube.

Reverse search finds most copies of a video on these sites, and the page reader learns little from them. But their
dates are exact and cheap: an X or TikTok post id contains the time it was created, and a YouTube page states its
upload date in its metadata. A copy of the same footage posted before the claimed date is the strongest evidence
there is against "this is happening now".
"""
import datetime as dt
import re

import requests

from . import replay

X_STATUS = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d{8,20})", re.I)
TIKTOK_VIDEO = re.compile(r"^https?://(?:www\.|m\.)?tiktok\.com/@[^/]+/(?:video|photo)/(\d{15,20})", re.I)
YOUTUBE = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)"
                     r"([A-Za-z0-9_-]{11})", re.I)
X_EPOCH_MS = 1288834974657  # X ("snowflake") ids: milliseconds since this moment, shifted left by 22 bits
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


def _day(seconds):
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).date().isoformat()


def from_id(url):
    """{'date', 'how'} for an X or TikTok post, from its id alone; None for other URLs."""
    m = X_STATUS.match(url or "")
    if m:
        pid = int(m.group(1))
        if pid > 1 << 32:  # ids before Nov 2010 were sequential and carry no time
            return {"date": _day(((pid >> 22) + X_EPOCH_MS) / 1000), "how": "X post id"}
        return None
    m = TIKTOK_VIDEO.match(url or "")
    if m:
        return {"date": _day(int(m.group(1)) >> 32), "how": "TikTok post id"}
    return None


def _youtube_fetch(vid):
    r = requests.get("https://www.youtube.com/watch?v=" + vid, headers={"User-Agent": UA, "Accept-Language": "en"},
                     cookies={"CONSENT": "YES+1", "SOCS": "CAI"}, timeout=20)
    m = re.search(r'"(?:uploadDate|publishDate)":"(\d{4}-\d{2}-\d{2})', r.text) if r.status_code == 200 else None
    return {"ok": r.status_code == 200, "date": m.group(1) if m else None}


def youtube(url):
    """{'date', 'how'} for a YouTube video from its page metadata, None otherwise (or if the lookup fails)."""
    m = YOUTUBE.match(url or "")
    if not m:
        return None
    try:
        j = replay.cached("ytdate", {"id": m.group(1)}, lambda: _youtube_fetch(m.group(1)),
                          keep=lambda r: r.get("ok"))
    except requests.RequestException:
        return None
    return {"date": j["date"], "how": "YouTube upload date"} if j.get("date") else None


def _x_thumb(pid):
    from . import xpost  # imported here: xpost is only needed for X copies
    try:
        j = replay.cached("xpost", {"id": pid}, lambda: xpost._fetch_json(pid), note="x post " + pid,
                          keep=lambda r: not r.get("missing"))
    except (requests.RequestException, xpost.PostError, ValueError):
        return None
    for m in j.get("mediaDetails", []) or []:
        if m.get("media_url_https"):
            return m["media_url_https"]
    return None


def _tiktok_fetch(url):
    r = requests.get("https://www.tiktok.com/oembed", params={"url": url}, headers={"User-Agent": UA}, timeout=20)
    return {"ok": r.status_code == 200, "thumb": (r.json().get("thumbnail_url") if r.status_code == 200 else None)}


def thumbnail(url):
    """The still image a copy shows (YouTube and TikTok cover image, X media preview), so the match checker can
    compare it with the post. Reverse search rarely returns an image for these pages, only the page."""
    m = YOUTUBE.match(url or "")
    if m:
        return "https://i.ytimg.com/vi/%s/hqdefault.jpg" % m.group(1)
    m = X_STATUS.match(url or "")
    if m:
        return _x_thumb(m.group(1))
    if TIKTOK_VIDEO.match(url or ""):
        try:
            return replay.cached("tiktok", {"url": url}, lambda: _tiktok_fetch(url), keep=lambda r: r.get("ok")).get("thumb")
        except (requests.RequestException, ValueError):
            return None
    return None


def is_post(url):
    return bool(X_STATUS.match(url or "") or TIKTOK_VIDEO.match(url or "") or YOUTUBE.match(url or ""))


def posted(url):
    return from_id(url) or youtube(url)

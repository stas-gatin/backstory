"""The archivist (no model): when did the Internet Archive first see a URL?

An archived copy is independent proof that the page or image file existed on that day. Requests are paced,
because the Wayback CDX API blocks clients that go faster than about 15 requests a minute.
"""
import datetime as dt
import threading
import time

import requests

from . import replay

CDX = "https://web.archive.org/cdx/search/cdx"
MIN_INTERVAL = 4.0
_lock = threading.Lock()
_last = [0.0]


def _fetch(url):
    for attempt in range(3):
        with _lock:
            wait = _last[0] + MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            r = requests.get(CDX, params={"url": url, "output": "json", "fl": "timestamp,original", "limit": 1},
                             timeout=30)
            if r.status_code == 200:
                rows = r.json() if r.text.strip() else []
                if len(rows) > 1:
                    return {"ok": True, "first": rows[1][0]}
                return {"ok": True, "first": None}
        except (requests.RequestException, ValueError):
            pass
        time.sleep(20 * (attempt + 1))
    return {"ok": False, "first": None}


def first_capture(url):
    """{'date': 'YYYY-MM-DD' or None, 'snapshot': archive URL or None, 'ok': lookup succeeded}."""
    res = replay.cached("wayback", {"url": url}, lambda: _fetch(url), note=url[:200], keep=lambda r: r["ok"])
    ts = res.get("first")
    if not ts:
        return {"date": None, "snapshot": None, "ok": res.get("ok", False)}
    day = dt.date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
    return {"date": day.isoformat(), "snapshot": "https://web.archive.org/web/%s/%s" % (ts, url), "ok": True}

"""Record and replay every external call (Meta models, image search, Internet Archive, web pages).

In live mode each answer is stored under replay/<kind>/<hash>.json, keyed by a hash of the request.
In replay mode only stored answers are used, so the app runs with no keys and no network, and gives the
same results that were recorded.
"""
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path

from . import config


class NotInReplay(Exception):
    """Replay mode and this request was never recorded."""


_lock = threading.Lock()


def request_hash(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _path(kind, h):
    return config.REPLAY_DIR / kind / h[:2] / (h + ".json")


# Other record stores to read from (colon-separated). An answer found there is copied into REPLAY_DIR, so a
# store for the demo can be assembled from earlier test runs and then works on its own.
EXTRA = [Path(d) for d in os.environ.get("BACKSTORY_REPLAY_EXTRA", "").split(":") if d]


def _copy_from_extra(rel):
    for d in EXTRA:
        src = d / rel
        if src.exists():
            dst = config.REPLAY_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            return dst
    return None


def lookup(kind, payload):
    p = _path(kind, request_hash(payload))
    if p.exists() or (EXTRA and _copy_from_extra(p.relative_to(config.REPLAY_DIR))):
        return json.loads(p.read_text())["response"]
    return None


def store(kind, payload, response, note=None):
    p = _path(kind, request_hash(payload))
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp%d" % threading.get_ident())
        tmp.write_text(json.dumps({"note": note, "response": response}, ensure_ascii=False, indent=1))
        os.replace(tmp, p)  # readers never see a half-written file


def cached_bytes(kind, payload, fetch):
    """Like cached(), for binary answers (downloaded media). fetch() returns bytes or None (not stored)."""
    p = config.REPLAY_DIR / kind / (request_hash(payload) + ".bin")
    if p.exists() or (EXTRA and _copy_from_extra(p.relative_to(config.REPLAY_DIR))):
        return p.read_bytes()
    if config.MODE != "live":
        raise NotInReplay(kind)
    data = fetch()
    if data:
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp%d" % threading.get_ident())
            tmp.write_bytes(data)
            os.replace(tmp, p)
    return data


def cached(kind, payload, fetch, note=None, keep=lambda r: True):
    """Return the stored answer for payload, or call fetch() (live mode only) and store it if keep(answer)."""
    hit = lookup(kind, payload)
    if hit is not None:
        return hit
    if config.MODE != "live":
        raise NotInReplay(kind)
    answer = fetch()
    if keep(answer):
        store(kind, payload, answer, note)
    return answer

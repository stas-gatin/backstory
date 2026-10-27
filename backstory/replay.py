"""Record and replay every external call (Meta models, image search, Internet Archive, web pages).

In live mode each answer is stored under replay/<kind>/<hash>.json, keyed by a hash of the request.
In replay mode only stored answers are used, so the app runs with no keys and no network, and gives the
same results that were recorded.
"""
import hashlib
import json
import threading

from . import config


class NotInReplay(Exception):
    """Replay mode and this request was never recorded."""


_lock = threading.Lock()


def request_hash(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _path(kind, h):
    return config.REPLAY_DIR / kind / h[:2] / (h + ".json")


def lookup(kind, payload):
    p = _path(kind, request_hash(payload))
    if p.exists():
        return json.loads(p.read_text())["response"]
    return None


def store(kind, payload, response, note=None):
    p = _path(kind, request_hash(payload))
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"note": note, "response": response}, ensure_ascii=False, indent=1))


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

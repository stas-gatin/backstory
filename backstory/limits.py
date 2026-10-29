"""Limits for live checks on a public copy: a few per visitor a day, a daily and a total spending cap, at most two at
a time, and a pause when the Meta Model API stops answering (for example when the credits run out).

Recorded examples are never limited: they cost nothing and keep the site useful when live checks are paused.
The counts live in a small JSON file, so a restart keeps them (a new deployment starts from zero).
"""
import datetime as dt
import json
import os
import re
import threading
from pathlib import Path

PER_VISITOR = int(os.environ.get("BACKSTORY_LIVE_PER_VISITOR", "3"))
DAY_USD = float(os.environ.get("BACKSTORY_LIVE_DAY_USD", "5"))
TOTAL_USD = float(os.environ.get("BACKSTORY_LIVE_TOTAL_USD", "40"))
AT_ONCE = int(os.environ.get("BACKSTORY_LIVE_AT_ONCE", "2"))
STATE = Path(os.environ.get("BACKSTORY_LIMITS_FILE", "/tmp/backstory_limits.json"))
# An answer like this from the Meta Model API means it will not take more calls for now.
OUT_OF_CREDIT = re.compile(r"HTTP (401|402|403|429)|insufficient|quota|credit|billing|exceeded", re.I)

_lock = threading.Lock()
_running = [0]


class Refused(Exception):
    pass


def _today():
    return dt.date.today().isoformat()


def _load():
    try:
        s = json.loads(STATE.read_text())
    except (OSError, ValueError):
        s = {}
    if s.get("day") != _today():
        s.update(day=_today(), day_usd=0.0, visitors={})
    s.setdefault("total_usd", 0.0)
    s.setdefault("paused", None)
    # A pause lasts half an hour: long enough to stop hammering a failing API, short enough to recover from a blip.
    if s["paused"] and s.get("paused_until", 0) < dt.datetime.now().timestamp():
        s["paused"] = None
    return s


def _save(s):
    try:
        STATE.write_text(json.dumps(s))
    except OSError:
        pass


def status(visitor):
    with _lock:
        s = _load()
        used = s["visitors"].get(visitor, 0)
        reason = (s["paused"] or ("today's budget for live checks is spent" if s["day_usd"] >= DAY_USD else None)
                  or ("the budget for live checks is spent" if s["total_usd"] >= TOTAL_USD else None))
        return {"live": reason is None, "reason": reason, "left": max(0, PER_VISITOR - used), "per_visitor": PER_VISITOR}


def start(visitor):
    """Reserve one live check for this visitor, or raise Refused with the reason."""
    with _lock:
        s = _load()
        if s["paused"]:
            raise Refused("Live checks are paused: %s. The recorded checks still work." % s["paused"])
        if s["day_usd"] >= DAY_USD or s["total_usd"] >= TOTAL_USD:
            raise Refused("Today's budget for live checks is spent. The recorded checks still work.")
        if s["visitors"].get(visitor, 0) >= PER_VISITOR:
            raise Refused("You have used your %d live checks for today. The recorded checks still work." % PER_VISITOR)
        if _running[0] >= AT_ONCE:
            raise Refused("Two live checks are already running. Please try again in a minute.")
        s["visitors"][visitor] = s["visitors"].get(visitor, 0) + 1
        _running[0] += 1
        _save(s)


def finish(usd, error_text=None):
    with _lock:
        _running[0] = max(0, _running[0] - 1)
        s = _load()
        s["day_usd"] += usd or 0.0
        s["total_usd"] += usd or 0.0
        if error_text and "Meta API call failed" in error_text and OUT_OF_CREDIT.search(error_text):
            s["paused"] = "the Meta Model API stopped answering"
            s["paused_until"] = dt.datetime.now().timestamp() + 1800
        _save(s)


def watch(events):
    """Pass a live check's events through, and count its cost (and any API failure) when it ends."""
    usd, err = 0.0, None
    try:
        for ev in events:
            if ev.get("type") in ("result", "error"):
                usd = (ev.get("cost") or {}).get("usd", 0.0)
            if ev.get("type") == "error":
                err = ev.get("text")
            yield ev
    finally:
        finish(usd, err)

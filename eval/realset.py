"""Test H2: run Backstory on real posts on X, from the link only.

eval/realset.json lists posts with a real photo or video: "fake" ones carry a false place/date/event caption and were
debunked by a professional fact-checker; "true" ones are news or official posts with a correct caption. Each post is
checked from its link alone, with fact-checking sites and debunk-looking URLs removed from the search results.
The X Community Note is never given to the agents.

Usage:
  python -m eval.realset --max-usd 6
Answers are recorded under runs/replay_h2/, so a second run costs nothing.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("BACKSTORY_REPLAY_DIR", str(ROOT / "runs" / "replay_h2"))

from backstory import pipeline  # noqa: E402


def run_one(post_url):
    result, steps = None, []
    for ev in pipeline.run(None, "", None, exclude_fact_checkers=True, post_url=post_url):
        if ev["type"] == "step" and ev["status"] == "done":
            steps.append("%s: %s" % (ev["agent"], ev["text"][:200]))
        if ev["type"] in ("result", "error"):
            result = ev
    return result or {"type": "error", "text": "no result"}, steps


def score(rows):
    out = {}
    for group in ("fake", "true"):
        for media in ("all", "photo", "video"):
            sel = [r for r in rows if r["group"] == group and media in ("all", r["media"])]
            if not sel:
                continue
            n = len(sel)
            out["%s_%s" % (group, media)] = {
                "n": n,
                "inconsistent": round(sum(r["verdict"] == "inconsistent" for r in sel) / n, 3),
                "cannot_tell": round(sum(r["verdict"] == "cannot_tell" for r in sel) / n, 3),
                "consistent": round(sum(r["verdict"] == "consistent" for r in sel) / n, 3),
                "errors": sum(r["verdict"] == "error" for r in sel)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(ROOT / "eval" / "realset.json"))
    ap.add_argument("--start", type=int, default=0, help="first position in the set (positions keep their numbers)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--media", choices=("photo", "video"), help="check only posts with this media")
    ap.add_argument("--max-usd", type=float, default=6.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", default=str(ROOT / "runs" / "test_h2.json"))
    a = ap.parse_args()
    items = json.load(open(a.set))[:a.limit]
    todo = [i for i in range(a.start, len(items)) if not a.media or items[i]["media"] == a.media]
    lock, rows, spent = threading.Lock(), [], [0.0]

    def job(i):
        item = items[i]
        with lock:
            if spent[0] >= a.max_usd:
                return
        res, steps = run_one(item["post_url"])
        usd = (res.get("cost") or {}).get("usd", 0)
        row = dict(item, i=i, verdict=res.get("verdict") if res["type"] == "result" else "error",
                   basis=res.get("basis"), summary=res.get("summary") or res.get("text"), actual=res.get("actual"),
                   community_note=bool(res.get("community_note")), grounds=res.get("grounds"),
                   cited_rows=[e for e in res.get("evidence") or [] if e["id"] in (res.get("cited") or [])],
                   steps=steps, usd=usd)
        with lock:
            spent[0] += usd
            rows.append(row)
            rows.sort(key=lambda r: r["i"])
            json.dump(rows, open(a.out, "w"), indent=1, ensure_ascii=False)
        print(i, item["group"], item["media"], "->", row["verdict"], "| $%.2f" % spent[0], flush=True)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(job, todo))
    if spent[0] >= a.max_usd:
        print("cost cap reached", flush=True)
    summary = dict(score(rows), usd=round(spent[0], 2), checked=len(rows), listed=len(todo))
    print(json.dumps(summary, indent=1), flush=True)
    json.dump({"summary": summary, "posts": rows}, open(a.out, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())

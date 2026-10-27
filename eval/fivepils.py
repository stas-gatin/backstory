"""Run the full Backstory pipeline on out-of-context cases from the 5Pils dataset.

5Pils (UKPLab, CC-BY-SA-4.0, https://github.com/UKPLab/5pils) lists real images that fact-checkers found used
with a false caption, with the false claim (claimed place + date) and the truth (true place + date), plus reverse
image search results collected in 2023. Each case is checked twice: once with the false claim, once with the true
one. Detection = share of false claims called "inconsistent"; false alarm = share of true claims called
"inconsistent" ("cannot_tell" is not a false alarm).

Usage:
  git clone https://github.com/UKPLab/5pils data/5pils
  python -m eval.fivepils --split val --limit 5
The answers are recorded under runs/replay_eval/, so a second run costs nothing.
"""
import argparse
import concurrent.futures as cf
import io
import json
import os
import re
import sys
import threading
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("BACKSTORY_REPLAY_DIR", str(ROOT / "runs" / "replay_eval"))

import requests  # noqa: E402
from PIL import Image  # noqa: E402

from backstory import pipeline, replay, search  # noqa: E402

NE = "not enough information"
# Pages whose URL gives the answer away (they are fact-checks of this very image).
LEAK = search.DEBUNK_URL
EXTRA_FACT_CHECKERS = ("211check.org newsmobile.in newsmeter.in thelogicalindian.com indiatoday.in "
                       "boomlive.in").split()


def allowed(url):
    host = search.domain(url)
    return not LEAK.search(url) and not any(host == d or host.endswith("." + d) for d in EXTRA_FACT_CHECKERS)


def load_cases(root, split):
    ev_by = defaultdict(list)
    for e in json.load(open(root / "dataset/retrieval_results/evidence_urls.json")):
        ev_by[e["image_path"]].append(e)
    rows = [x for x in json.load(open(root / ("dataset/%s.json" % split)))
            if x["type_of_image"] == "out-of-context" and NE not in (x["claimed_date"], x["date"])]
    cases = []
    for x in rows:
        if not ev_by.get(x["image_path"]) or not re.search(r"(19|20)\d\d", x["claimed_date"]):
            continue
        pages = []
        for e in ev_by[x["image_path"]]:
            if allowed(e["raw_url"]) and e["raw_url"] not in [p["url"] for p in pages]:
                imgs = [u for u in e.get("image_urls", []) if allowed(u)]
                pages.append({"url": e["raw_url"], "title": "", "image_urls": imgs, "match": "full"})
        cases.append({"x": x, "pages": pages})
    return rows, cases


def get_image(url, cache_dir, k):
    fn = cache_dir / ("%03d.jpg" % k)
    if not fn.exists():
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (research evaluation)"}, timeout=30)
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((1024, 1024))
        im.save(fn, quality=88)
    return fn.read_bytes()


def import_wayback(path):
    """Reuse earlier Internet Archive lookups (url -> first capture timestamp or null) in the eval replay store."""
    n = 0
    for url, ts in json.load(open(path)).items():
        if replay.lookup("wayback", {"url": url}) is None:
            replay.store("wayback", {"url": url}, {"ok": True, "first": ts}, note=url[:200])
            n += 1
    return n


def run_one(image, caption, pages):
    result, steps = None, []
    for ev in pipeline.run(image, caption, posted_on="unknown", matches=pages, exclude_fact_checkers=True):
        if ev["type"] == "step" and ev["status"] == "done":
            steps.append("%s: %s" % (ev["agent"], ev["text"][:160]))
        if ev["type"] in ("result", "error"):
            result = ev
    return result, steps


class Spend:
    """Total spend across worker threads; no new check starts once the cap is reached."""

    def __init__(self, cap):
        self.cap, self.usd, self.lock = cap, 0.0, threading.Lock()

    def add(self, usd):
        with self.lock:
            self.usd += usd

    def over(self):
        with self.lock:
            return self.usd >= self.cap


def check_case(k, case, image, spend):
    x = case["x"]
    row = {"k": k, "url": x["URL"]}
    for tag, place, date in (("false", x["claimed_location"], x["claimed_date"]),
                             ("true", x["location"], x["date"])):
        if spend.over():
            row[tag] = {"verdict": "skipped (cost cap)"}
            continue
        # 5Pils gives place and date separately; the caption is written from them.
        caption = "Photo taken in %s." % ", ".join(v for v in (place, date) if v != NE)
        try:
            res, steps = run_one(image, caption, case["pages"])
        except Exception as e:  # noqa: BLE001
            res, steps = {"type": "error", "text": "%s: %s" % (type(e).__name__, e)}, []
        res = res or {"type": "error", "text": "no result"}
        spend.add((res.get("cost") or {}).get("usd", 0))
        row[tag] = {"caption": caption, "verdict": res.get("verdict") if res["type"] == "result" else "error",
                    "basis": res.get("basis"), "rule_fired": bool(res.get("rule")),
                    "summary": res.get("summary") or res.get("text"), "steps": steps, "cost": res.get("cost")}
    return row


def score(out):
    done = [r for r in out if "caption" in r["false"] and "caption" in r["true"]]
    n = len(done)
    if not n:
        return {"n": 0}
    share = lambda tag, f: round(sum(f(r[tag]) for r in done) / n, 3)  # noqa: E731
    return {"n": n,
            "detection": share("false", lambda v: v["verdict"] == "inconsistent"),
            "false_alarm": share("true", lambda v: v["verdict"] == "inconsistent"),
            "cannot_tell_false": share("false", lambda v: v["verdict"] == "cannot_tell"),
            "cannot_tell_true": share("true", lambda v: v["verdict"] == "cannot_tell"),
            "errors": sum(v["verdict"] == "error" for r in done for v in (r["false"], r["true"])),
            "rule_detection": share("false", lambda v: v["rule_fired"]),
            "rule_false_alarm": share("true", lambda v: v["rule_fired"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/5pils"))
    ap.add_argument("--split", default="val")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-usd", type=float, default=2.0)
    ap.add_argument("--images-dir", help="folder with NNN.jpg per case index (default: download into runs/)")
    ap.add_argument("--wayback-cache", help="JSON url -> first capture timestamp, imported before the run")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.data)
    rows, cases = load_cases(root, a.split)
    cache_dir = Path(a.images_dir) if a.images_dir else ROOT / "runs" / ("images_%s" % a.split)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_f = Path(a.out) if a.out else ROOT / "runs" / ("fivepils_%s.json" % a.split)
    print("eligible %d, with search results %d" % (len(rows), len(cases)), flush=True)
    if a.wayback_cache:
        print("imported %d archive lookups" % import_wayback(a.wayback_cache), flush=True)
    spend, out, lock = Spend(a.max_usd), [], threading.Lock()

    def job(k):
        try:
            image = get_image(cases[k]["x"]["image_URL"], cache_dir, k)
        except Exception as e:  # noqa: BLE001
            print(k, "image unavailable:", type(e).__name__, flush=True)
            return
        if spend.over():
            return
        row = check_case(k, cases[k], image, spend)
        with lock:
            out.append(row)
            out.sort(key=lambda r: r["k"])
            json.dump(out, open(out_f, "w"), indent=1, ensure_ascii=False)
        print(k, "false:", row["false"]["verdict"], "|", "true:", row["true"]["verdict"], "| $%.2f" % spend.usd,
              flush=True)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(job, range(len(cases[:a.limit]))))
    if spend.over():
        print("cost cap reached", flush=True)
    summary = dict(score(out), usd=round(spend.usd, 2))
    print(json.dumps(summary), flush=True)
    json.dump({"summary": summary, "cases": out}, open(out_f, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())

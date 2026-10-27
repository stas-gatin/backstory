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
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("BACKSTORY_REPLAY_DIR", str(ROOT / "runs" / "replay_eval"))

import requests  # noqa: E402
from PIL import Image  # noqa: E402

from backstory import pipeline, search  # noqa: E402

NE = "not enough information"
# Pages whose URL gives the answer away (they are fact-checks of this very image).
LEAK = re.compile(r"fact-?check|fake|hoax|misleading|false|debunk|verif", re.I)
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


def run_one(image, caption, pages):
    result, steps = None, []
    for ev in pipeline.run(image, caption, posted_on="unknown", matches=pages, exclude_fact_checkers=True):
        if ev["type"] == "step" and ev["status"] == "done":
            steps.append("%s: %s" % (ev["agent"], ev["text"][:160]))
        if ev["type"] in ("result", "error"):
            result = ev
    return result, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/5pils"))
    ap.add_argument("--split", default="val")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-usd", type=float, default=2.0)
    a = ap.parse_args()
    root = Path(a.data)
    rows, cases = load_cases(root, a.split)
    cache_dir = ROOT / "runs" / ("images_%s" % a.split)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_f = ROOT / "runs" / ("fivepils_%s.json" % a.split)
    print("eligible %d, with search results %d" % (len(rows), len(cases)), flush=True)
    out, spent = [], 0.0
    for k, case in enumerate(cases[:a.limit]):
        if spent >= a.max_usd:
            print("cost cap reached", flush=True)
            break
        x = case["x"]
        try:
            image = get_image(x["image_URL"], cache_dir, k)
        except Exception as e:  # noqa: BLE001
            print(k, "image download failed:", type(e).__name__, flush=True)
            continue
        row = {"k": k, "url": x["URL"]}
        for tag, place, date in (("false", x["claimed_location"], x["claimed_date"]),
                                 ("true", x["location"], x["date"])):
            # 5Pils gives place and date separately; the caption is written from them.
            caption = "Photo taken in %s." % ", ".join(v for v in (place, date) if v != NE)
            res, steps = run_one(image, caption, case["pages"])
            spent += (res or {}).get("cost", {}).get("usd", 0)
            row[tag] = {"caption": caption, "verdict": res.get("verdict") if res["type"] == "result" else "error",
                        "basis": res.get("basis"), "summary": res.get("summary") or res.get("text"),
                        "steps": steps, "cost": res.get("cost")}
        out.append(row)
        print(k, "false:", row["false"]["verdict"], "|", "true:", row["true"]["verdict"], "| $%.2f" % spent,
              flush=True)
        json.dump(out, open(out_f, "w"), indent=1, ensure_ascii=False)
    n = len(out)
    if n:
        det = sum(r["false"]["verdict"] == "inconsistent" for r in out) / n
        fa = sum(r["true"]["verdict"] == "inconsistent" for r in out) / n
        print(json.dumps({"n": n, "detection": round(det, 3), "false_alarm": round(fa, 3), "usd": round(spent, 2)}))


if __name__ == "__main__":
    sys.exit(main())

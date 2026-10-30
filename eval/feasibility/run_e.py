"""Test E (see PREREG_E.md). Usage: run_e.py val|test [limit]. Writes runs/test_e_<split>.json."""
import base64, calendar, datetime as dt, io, json, os, re, sys, time
from collections import defaultdict
from urllib.parse import urlparse
import requests
from PIL import Image
from samclient import API, load_key, extract_text
from check_c import parse_json

CAP, PIN, POUT = 3.0, 1.25e-6, 4.25e-6
spent = {"usd": 0.0, "calls": 0, "in": 0, "out": 0}
NE = "not enough information"
FC = ("factly.in pesacheck.org 211check.org africacheck.org afp.com boomlive.in altnews.in newschecker.in thequint.com "
      "vishvasnews.com indiatoday.in snopes.com reuters.com factcheck.org politifact.com newsmobile.in newsmeter.in "
      "thelogicalindian.com fullfact.org logicallyfacts.com misbar.com dubawa.org faktisk.no").split()
LEAK = re.compile(r"fact-?check|fake|hoax|misleading|false|debunk|verif", re.I)
MON = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MON.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
UA = {"User-Agent": "Mozilla/5.0 (research test)"}

def period_start(s):
    s = s or ""
    full = []
    for m in re.finditer(r"(\d{4})-(\d\d)-(\d\d)", s): full.append((m.start(), int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"(\d{1,2})(?:st|nd|rd|th)? ([A-Za-z]+),? (\d{4})", s):
        if m[2].lower() in MON: full.append((m.start(), int(m[3]), MON[m[2].lower()], int(m[1])))
    for m in re.finditer(r"([A-Za-z]+) (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})", s):
        if m[1].lower() in MON: full.append((m.start(), int(m[3]), MON[m[1].lower()], int(m[2])))
    for pos, y, mo, d in sorted(full):
        try: return dt.date(y, mo, d)
        except ValueError: pass
    for m in re.finditer(r"([A-Za-z]+),? (\d{4})", s):
        if m[1].lower() in MON: return dt.date(int(m[2]), MON[m[1].lower()], 1)
    m = re.search(r"\b(19|20)\d\d\b", s)
    return dt.date(int(m[0]), 1, 1) if m else None

def allowed(url):
    host = urlparse(url).netloc.lower()
    return not any(host == d or host.endswith("." + d) for d in FC) and not LEAK.search(url)

CACHE_F = "runs/wayback_cache.json"
cache = json.load(open(CACHE_F)) if os.path.exists(CACHE_F) else {}
def first_capture(url, tries=6):
    """Earliest Wayback capture (YYYYMMDDhhmmss) or None. Paced to about 12 requests a minute (CDX rate limit)."""
    if url in cache: return cache[url]
    for a in range(tries):
        time.sleep(5)
        try:
            r = requests.get("https://web.archive.org/cdx/search/cdx", params={"url": url, "output": "json", "fl": "timestamp", "limit": 1}, timeout=30)
            if r.status_code == 200:
                j = r.json() if r.text.strip() else []
                cache[url] = j[1][0] if len(j) > 1 else None
                return cache[url]
        except Exception:
            pass
        time.sleep(60)  # blocked or failed: back off
    return None  # lookup failed: not cached, counts as no capture

def to_date(ts): return dt.date(int(ts[:4]), int(ts[4:6]), int(ts[6:8])) if ts else None

def spark(path, claim, evidence):
    per = spent["usd"] / spent["calls"] if spent["calls"] else 0.01
    if spent["usd"] + 2 * per > CAP: raise SystemExit("cost cap reached")
    ev = "\n".join("- %s | page first archived: %s | image first archived: %s | %s" % (e["domain"], e["page_first"] or "never", e["img_first"] or "never", e["url"][:160]) for e in evidence) or "(no evidence found)"
    text = ('Claim about this photo: "It was taken in %s, %s."\nReverse image search found the photo on these pages '
            '(Internet Archive first-capture dates):\n%s\n\nIs the claim consistent with the photo and this evidence? '
            'A photo that was online before the claimed event cannot show that event. Reply with one JSON object only: '
            '{"verdict": "consistent" | "inconsistent" | "cannot_tell", "reason": "short"}') % (claim[0], claim[1], ev)
    img = "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()
    body = {"model": "muse-spark-1.3", "stream": False, "reasoning": {"effort": "low"},
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": img}]}]}
    h = {"Authorization": "Bearer " + load_key(), "Content-Type": "application/json"}
    for a in range(3):
        r = requests.post(API, headers=h, data=json.dumps(body), timeout=180)
        if r.status_code == 200: break
        time.sleep(3 * (a + 1))
    r.raise_for_status()
    j = r.json(); u = j.get("usage", {})
    spent["in"] += u.get("input_tokens", 0); spent["out"] += u.get("output_tokens", 0); spent["calls"] += 1
    spent["usd"] = spent["in"] * PIN + spent["out"] * POUT
    return parse_json(extract_text(j))

def get_image(x, k, folder):
    fn = "%s/%03d.jpg" % (folder, k)
    if os.path.exists(fn): return fn
    try:
        r = requests.get(x["image_URL"], headers=UA, timeout=30)
        im = Image.open(io.BytesIO(r.content)).convert("RGB"); im.thumbnail((768, 768)); im.save(fn, quality=85)
        return fn
    except Exception:
        return None

if __name__ == "__main__":
    split = sys.argv[1]; limit = int(sys.argv[2]) if len(sys.argv) > 2 else None; use_llm = "--no-llm" not in sys.argv
    ev_by = defaultdict(list)
    for e in json.load(open("data/5pils/dataset/retrieval_results/evidence_urls.json")): ev_by[e["image_path"]].append(e)
    all_rows = [x for x in json.load(open("data/5pils/dataset/%s.json" % split)) if x["type_of_image"] == "out-of-context" and NE not in (x["claimed_date"], x["date"])]
    cases = [x for x in all_rows if ev_by.get(x["image_path"]) and re.search(r"(19|20)\d\d", x["claimed_date"])]
    print("eligible", len(all_rows), "cases", len(cases), flush=True)
    folder = "data/5pils_e_%s" % split; os.makedirs(folder, exist_ok=True)
    out = []
    try:
        for k, x in enumerate(cases[:limit]):
            pages, imgs = [], []
            for e in ev_by[x["image_path"]]:
                if allowed(e["raw_url"]) and e["raw_url"] not in [p["url"] for p in pages]:
                    pages.append({"url": e["raw_url"], "domain": urlparse(e["raw_url"]).netloc, "imgs": [u for u in e.get("image_urls", []) if allowed(u)]})
            pages = pages[:5] + pages[5:]
            evidence, n_img = [], 0
            for i, p in enumerate(pages):
                pf = first_capture(p["url"]) if i < 5 else None
                img_first = None
                for u in p["imgs"]:
                    if n_img >= 10: break
                    n_img += 1; t = first_capture(u)
                    if t and (img_first is None or t < img_first): img_first = t
                if i < 5 or img_first:
                    evidence.append({"url": p["url"], "domain": p["domain"], "page_first": str(to_date(pf)) if pf else None, "img_first": str(to_date(img_first)) if img_first else None})
            json.dump(cache, open(CACHE_F, "w"))
            img_dates = [dt.date.fromisoformat(e["img_first"]) for e in evidence if e["img_first"]]
            earliest = min(img_dates) if img_dates else None
            row = {"k": k, "url": x["URL"], "evidence": evidence, "earliest_img": str(earliest) if earliest else None}
            path = get_image(x, k, folder) if use_llm else None
            for tag, loc, date in (("false", x["claimed_location"], x["claimed_date"]), ("true", x["location"], x["date"])):
                start = period_start(date)
                P = "inconsistent" if (earliest and start and earliest < start - dt.timedelta(days=1)) else "cannot_tell"
                S = None
                if use_llm and path:
                    try: S = spark(path, (loc, date), evidence).get("verdict")
                    except SystemExit: raise
                    except Exception as e: S = "error"
                AL = "inconsistent" if P == "inconsistent" else S
                row[tag] = {"start": str(start), "P": P, "S": S, "AL": AL}
            out.append(row)
            print(k, "earliest", row["earliest_img"], "| F", row["false"]["start"], row["false"]["P"], row["false"]["S"], "| T", row["true"]["start"], row["true"]["P"], row["true"]["S"], "| $%.2f" % spent["usd"], flush=True)
            json.dump({"spent": spent, "rows": out}, open("runs/test_e_%s.json" % split, "w"), indent=1)
    except SystemExit as e:
        print(e)
    n = len(out); res = {"n": n, "eligible_all": len(all_rows), "spent_usd": round(spent["usd"], 3), "calls": spent["calls"]}
    for arm in ("P", "S", "AL"):
        res[arm + "_detect"] = round(sum(r["false"][arm] == "inconsistent" for r in out) / n, 3)
        res[arm + "_false_alarm"] = round(sum(r["true"][arm] == "inconsistent" for r in out) / n, 3)
    res["S_missing"] = sum(r["false"]["S"] in (None, "error") or r["true"]["S"] in (None, "error") for r in out)
    print(json.dumps(res))
    json.dump({"spent": spent, "rows": out, "result": res}, open("runs/test_e_%s.json" % split, "w"), indent=1)

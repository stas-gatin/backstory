"""Test D (see PREREG_D.md). Hard cost cap 0.30 USD. Writes runs/test_d.json."""
import base64, calendar, datetime as dt, json, re, time
import requests
from samclient import API, load_key, extract_text
from check_c import parse_json, solar_elev

CAP, PIN, POUT = 0.30, 1.25e-6, 4.25e-6
spent = {"usd": 0.0, "calls": 0, "in": 0, "out": 0}

PROMPT = """Claim about this photo: "It was taken in {loc}, {date}."
Using only what you can see in the photo, is the claim consistent with it? Reply with one JSON object only:
{{"verdict": "consistent" | "inconsistent" | "cannot_tell",
 "contradictions": [{{"type": "time_of_day|weather|season|snow|language_or_signs|landmark_or_place|era_or_technology|other",
   "evidence": "what you see, short"}}],
 "seen": {{"sun": "high|low|below_horizon|not_visible", "falling_precipitation": "rain|snow|none|unknown",
   "sky": "clear|overcast|not_visible", "snow_on_ground": "yes|no|unknown",
   "deciduous_foliage": "full_green|autumn|leafless|not_visible"}}}}
List a contradiction only if something visible conflicts with the claim; otherwise an empty list."""

def call(path, loc, date):
    per_call = spent["usd"] / spent["calls"] if spent["calls"] else 0.006
    if spent["usd"] + 2 * per_call > CAP:
        raise SystemExit("cost cap reached")
    img = "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()
    body = {"model": "muse-spark-1.3", "stream": False, "reasoning": {"effort": "low"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": PROMPT.format(loc=loc, date=date)}, {"type": "input_image", "image_url": img}]}]}
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

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
def parse_date(s):
    """Return (date or None for the day, (year, month) or None)."""
    s = s.strip()
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", s)
    if m: d = dt.date(*map(int, m.groups())); return d, (d.year, d.month)
    m = re.match(r"(\d{1,2}) ([A-Za-z]+),? (\d{4})$", s) or None
    if m and m.group(2).lower() in MONTHS: d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))); return d, (d.year, d.month)
    m = re.match(r"([A-Za-z]+) (\d{1,2}),? (\d{4})$", s)
    if m and m.group(1).lower() in MONTHS: d = dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))); return d, (d.year, d.month)
    m = re.match(r"([A-Za-z]+),? (\d{4})$", s)
    if m and m.group(1).lower() in MONTHS: return None, (int(m.group(2)), MONTHS[m.group(1).lower()])
    return None, None

def geocode(loc):
    for q in [loc] + [p.strip() for p in re.split(r"[,;]", loc)]:
        if not q or len(q) > 60: continue
        j = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": q, "count": 1}, timeout=30).json()
        if j.get("results"): r = j["results"][0]; return r["latitude"], r["longitude"]
    return None

def archive(lat, lon, start, end):
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=%.3f&longitude=%.3f&start_date=%s&end_date=%s"
           "&daily=precipitation_sum,temperature_2m_mean,temperature_2m_min,cloud_cover_mean&timezone=auto" % (lat, lon, start, end))
    time.sleep(0.4)
    return requests.get(url, timeout=60).json().get("daily")

def check_physical(resp, loc, date):
    """Arm A: drop physical contradictions that the archive refutes. Returns (kept, refuted, applicable)."""
    day, ym = parse_date(date); geo = geocode(loc) if (day or ym) else None
    seen = resp.get("seen", {}); kept, refuted, applicable = [], [], False
    for c in resp.get("contradictions", []):
        t = c.get("type")
        if t not in ("time_of_day", "weather", "season", "snow") or not geo:
            kept.append(c); continue
        lat, lon = geo
        if t == "weather" and day:
            d = archive(lat, lon, (day - dt.timedelta(days=1)).isoformat(), (day + dt.timedelta(days=1)).isoformat())
            if d: applicable = True
            ok = d and ((seen.get("falling_precipitation") == "rain" and sum(x or 0 for x in d["precipitation_sum"]) >= 1)
                        or (seen.get("sky") == "clear" and d["cloud_cover_mean"][1] < 50))
            (refuted if ok else kept).append(c); continue
        if t in ("season", "snow") and ym:
            last = calendar.monthrange(*ym)[1]
            d = archive(lat, lon, "%d-%02d-01" % ym, "%d-%02d-%02d" % (ym[0], ym[1], last))
            if not d: kept.append(c); continue
            applicable = True
            mean = sum(d["temperature_2m_mean"]) / len(d["temperature_2m_mean"]); tmin = min(d["temperature_2m_min"])
            f = seen.get("deciduous_foliage")
            ok = ((seen.get("snow_on_ground") == "yes" and tmin <= 2) or (f == "full_green" and mean >= 10)
                  or (f == "leafless" and mean <= 10))
            (refuted if ok else kept).append(c); continue
        kept.append(c)  # time_of_day needs an hour, none of the claims has one
    return kept, refuted, applicable

def arm_a(resp, kept, refuted):
    if kept: return "inconsistent"
    if refuted and resp.get("verdict") == "inconsistent": return "cannot_tell"
    return resp.get("verdict")

if __name__ == "__main__":
    cases = json.load(open("data/5pils_img/cases.json")); out = []
    try:
        for c in cases:
            row = {"file": c["file"]}
            for tag, loc, date in (("false", c["claimed_location"], c["claimed_date"]), ("true", c["location"], c["date"])):
                resp = call(c["file"], loc, date)
                kept, refuted, app = check_physical(resp, loc, date)
                row[tag] = {"B": resp.get("verdict"), "A": arm_a(resp, kept, refuted), "applicable": app,
                            "contradictions": resp.get("contradictions", []), "refuted": refuted}
            out.append(row)
            print(c["file"], "F:", row["false"]["B"], row["false"]["A"], "| T:", row["true"]["B"], row["true"]["A"],
                  "| $%.3f" % spent["usd"], flush=True)
            json.dump({"spent": spent, "rows": out}, open("runs/test_d.json", "w"), indent=1)
    except SystemExit as e:
        print(e)
    n = len(out)
    res = {"n": n, "spent_usd": round(spent["usd"], 3), "calls": spent["calls"]}
    for arm in "BA":
        res[arm + "_detect"] = round(sum(r["false"][arm] == "inconsistent" for r in out) / n, 2)
        res[arm + "_false_alarm"] = round(sum(r["true"][arm] == "inconsistent" for r in out) / n, 2)
    res["applicability"] = round(sum(r["false"]["applicable"] for r in out) / n, 2)
    print(json.dumps(res))
    json.dump({"spent": spent, "rows": out, "result": res}, open("runs/test_d.json", "w"), indent=1)

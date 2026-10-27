"""Test C (see PREREG_C.md). Rules below are fixed before the run."""
import base64, datetime as dt, json, math, random, sys, time
import requests
from samclient import API, load_key, extract_text

MODEL = "muse-spark-1.3"

def spark(content, retries=4):
    body = {"model": MODEL, "input": [{"type": "message", "role": "user", "content": content}], "stream": False}
    h = {"Authorization": "Bearer " + load_key(), "Content-Type": "application/json"}
    last = None
    for a in range(retries):
        r = requests.post(API, headers=h, data=json.dumps(body), timeout=180)
        if r.status_code == 200:
            return extract_text(r.json())
        last = (r.status_code, r.text[:200]); time.sleep(3 * (a + 1))
    raise RuntimeError(last)

def img(path):
    return {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()}

def parse_json(t):
    s, e = t.find("{"), t.rfind("}")
    return json.loads(t[s:e + 1])

OBS_PROMPT = """Look at this photo and report only what is visible. Answer with one JSON object:
{"outdoor": true/false, "judgeable": true/false (false if it is a close-up, artwork, or the sky/ground/light cannot be seen),
 "light": "full_daylight" | "twilight" | "night" | "unknown",
 "shadows": "hard" | "soft_or_none" | "unknown",
 "falling_precipitation": "rain" | "snow" | "none" | "unknown",
 "snow_on_ground": "covered" | "patches" | "none" | "unknown",
 "grass_or_bare_ground_visible": true/false,
 "deciduous_broadleaf_trees": "full_green" | "autumn_colours" | "leafless" | "budding" | "not_visible" | "unknown"}
Use "unknown" whenever you are not sure. Do not guess the date."""

def solar_elev(lat, lon, utc):
    d = utc.timetuple().tm_yday; hr = utc.hour + utc.minute / 60
    g = 2 * math.pi / 365 * (d - 1 + (hr - 12) / 24)
    decl = 0.006918 - 0.399912*math.cos(g) + 0.070257*math.sin(g) - 0.006758*math.cos(2*g) + 0.000907*math.sin(2*g) - 0.002697*math.cos(3*g) + 0.00148*math.sin(3*g)
    eqt = 229.18*(0.000075 + 0.001868*math.cos(g) - 0.032077*math.sin(g) - 0.014615*math.cos(2*g) - 0.040849*math.sin(2*g))
    tst = hr*60 + eqt + 4*lon
    ha = math.radians(tst/4 - 180); la = math.radians(lat)
    cz = math.sin(la)*math.sin(decl) + math.cos(la)*math.cos(decl)*math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1, min(1, cz))))

_wcache = {}
def weather(lat, lon, day):
    key = (round(lat, 3), round(lon, 3), day)
    if key in _wcache: return _wcache[key]
    start = (day - dt.timedelta(days=30)).isoformat(); end = (day + dt.timedelta(days=1)).isoformat()
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=%.4f&longitude=%.4f&start_date=%s&end_date=%s"
           "&hourly=temperature_2m,precipitation,snowfall,snow_depth,cloud_cover&timezone=auto" % (lat, lon, start, end))
    for a in range(5):
        r = requests.get(url, timeout=60)
        if r.status_code == 200: break
        time.sleep(5 * (a + 1))
    j = r.json(); _wcache[key] = j; time.sleep(0.5)
    return j

def check(obs, lat, lon, local):
    """Return list of fired rules. local = naive local datetime of the claim."""
    w = weather(lat, lon, local.date())
    hh = w["hourly"]; times = [dt.datetime.fromisoformat(t) for t in hh["time"]]
    idx = {t: i for i, t in enumerate(times)}
    i = idx.get(local.replace(minute=0))
    utc = local - dt.timedelta(seconds=w["utc_offset_seconds"])
    el = solar_elev(lat, lon, utc)
    fired = []
    if obs.get("light") == "night" and el > 3: fired.append("R1 night seen, sun %.0f deg up" % el)
    if obs.get("light") == "full_daylight" and el < -4: fired.append("R1 daylight seen, sun %.0f deg below" % el)
    if obs.get("shadows") == "hard" and el < 0: fired.append("R2 hard shadows, sun below horizon")
    if obs.get("shadows") == "hard" and i is not None and all((hh["cloud_cover"][k] or 0) >= 98 for k in (i-1, i, i+1)):
        fired.append("R2 hard shadows, archive overcast 98%+")
    day_i = [k for k, t in enumerate(times) if t.date() == local.date()]
    prev7 = [k for k, t in enumerate(times) if local - dt.timedelta(days=7) <= t <= local]
    prev21 = [k for k, t in enumerate(times) if local - dt.timedelta(days=21) <= t <= local]
    sd = [hh["snow_depth"][k] or 0 for k in day_i]
    if obs.get("snow_on_ground") == "covered" and max(sd) == 0 and max(hh["temperature_2m"][k] for k in prev7) > 8:
        fired.append("R3 snow cover seen, archive no snow and warm week")
    if obs.get("snow_on_ground") == "none" and obs.get("grass_or_bare_ground_visible") and min(sd) >= 0.20:
        fired.append("R3 no snow seen, archive snow depth %.2f m" % min(sd))
    if obs.get("falling_precipitation") == "snow" and i is not None and hh["temperature_2m"][i] > 6:
        fired.append("R4 falling snow at %.0f C" % hh["temperature_2m"][i])
    if obs.get("falling_precipitation") == "rain":
        near = [k for k, t in enumerate(times) if abs((t.date() - local.date()).days) <= 1]
        if sum(hh["precipitation"][k] or 0 for k in near) < 0.1: fired.append("R4 rain seen, archive dry 3 days")
    mt = sum(hh["temperature_2m"][k] for k in prev21) / len(prev21)
    if obs.get("deciduous_broadleaf_trees") == "full_green" and mt < 2: fired.append("R5 green leaves, 21-day mean %.1f C" % mt)
    if obs.get("deciduous_broadleaf_trees") == "leafless" and mt > 17: fired.append("R5 leafless, 21-day mean %.1f C" % mt)
    return fired, round(el, 1)

def false_claim(local, rng):
    m = rng.randint(4, 8) * rng.choice([-1, 1]); h = rng.randint(5, 10) * rng.choice([-1, 1])
    y, mo = local.year, local.month + m
    while mo < 1: mo += 12; y -= 1
    while mo > 12: mo -= 12; y += 1
    d = min(local.day, 28)
    return (dt.datetime(y, mo, d, local.hour) + dt.timedelta(hours=h)).replace(minute=0)

def baseline(path, city, lat, lon, local):
    q = ("Claim: this photo was taken in %s (lat %.3f, lon %.3f) on %s at about %02d:00 local time. "
         "Using only what you can see in the photo, is the claim consistent with the photo? Answer with one JSON "
         "object {\"answer\": \"consistent\" | \"inconsistent\" | \"cannot_tell\", \"reason\": \"...\"}."
         % (city, lat, lon, local.strftime("%d %B %Y"), local.hour))
    return parse_json(spark([{"type": "input_text", "text": q}, img(path)]))

if __name__ == "__main__":
    meta = json.load(open("data/commons/meta.json")); rng = random.Random(1)
    rows = []
    for r in meta:
        true_local = dt.datetime.strptime(r["exif"], "%Y:%m:%d %H:%M").replace(minute=0)
        fake_local = false_claim(true_local, rng)
        try:
            obs = parse_json(spark([{"type": "input_text", "text": OBS_PROMPT}, img(r["file"])]))
        except Exception as e:
            print(r["file"], "obs fail", e); continue
        row = {"file": r["file"], "city": r["city"], "obs": obs}
        if not (obs.get("outdoor") and obs.get("judgeable")):
            row["dropped"] = True; rows.append(row); print(r["file"], "dropped"); continue
        for tag, local in (("true", true_local), ("false", fake_local)):
            fired, el = check(obs, r["lat"], r["lon"], local)
            b = baseline(r["file"], r["city"], r["lat"], r["lon"], local)
            row[tag] = {"claim": local.isoformat(), "sun": el, "G": fired, "B": b.get("answer"), "B_reason": b.get("reason", "")[:200]}
        rows.append(row)
        print(r["file"], "T:", row["true"]["G"], row["true"]["B"], "| F:", row["false"]["G"], row["false"]["B"], flush=True)
        json.dump(rows, open("runs/test_c.json", "w"), indent=1)
    kept = [x for x in rows if not x.get("dropped")]
    n = len(kept)
    gd = sum(bool(x["false"]["G"]) for x in kept) / n; gf = sum(bool(x["true"]["G"]) for x in kept) / n
    bd = sum(x["false"]["B"] == "inconsistent" for x in kept) / n; bf = sum(x["true"]["B"] == "inconsistent" for x in kept) / n
    keep = gf <= 0.10 and gd >= 0.50 and (gd - bd >= 0.15 or bf - gf >= 0.15)
    print(json.dumps({"n": n, "dropped": len(rows) - n, "G_detect": gd, "G_false_alarm": gf, "B_detect": bd, "B_false_alarm": bf, "KEEP": keep}))

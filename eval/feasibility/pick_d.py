"""Pick 30 out-of-context 5Pils test cases with downloadable images (seed 4). Writes data/5pils_img/cases.json."""
import io, json, random
import requests
from PIL import Image
NE = "not enough information"
rows = [x for x in json.load(open("data/5pils/dataset/test.json"))
        if x["type_of_image"] == "out-of-context" and NE not in (x["date"], x["claimed_date"], x["location"], x["claimed_location"])]
print("eligible", len(rows))
random.Random(4).shuffle(rows)
UA = {"User-Agent": "Mozilla/5.0 (research test)"}
cases = []
for x in rows:
    if len(cases) >= 30: break
    try:
        r = requests.get(x["image_URL"], headers=UA, timeout=30)
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print("skip", x["image_URL"][:80], type(e).__name__); continue
    im.thumbnail((768, 768))
    fn = "data/5pils_img/%02d.jpg" % len(cases)
    im.save(fn, quality=85)
    cases.append({"file": fn, "url": x["URL"], "claim_text": x["claim"], "claimed_location": x["claimed_location"],
                  "claimed_date": x["claimed_date"], "location": x["location"], "date": x["date"]})
json.dump(cases, open("data/5pils_img/cases.json", "w"), indent=1)
print("picked", len(cases))

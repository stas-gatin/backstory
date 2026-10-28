"""Build the demo cases the web app replays: run each case once and record every answer.

Answers already recorded by the tests are reused (BACKSTORY_REPLAY_EXTRA); anything missing is asked live, so the
demo shows exactly what the current pipeline does. The photos and videos are third-party media: they stay in the
local, gitignored demo folder and are never committed.

Usage:
  BACKSTORY_REPLAY_DIR=runs/replay_demo BACKSTORY_REPLAY_EXTRA=runs/replay_h2:runs/replay_h3:... \\
    python -m eval.build_demo --out runs/demo --local runs/examples_local
"""
import argparse
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

from backstory import pipeline, video, xpost

DEMOS = [
    {"id": "la_fires", "kind": "link", "title": "\"LA fires\" freeway video",
     "blurb": "A freeway lined with flames, shared during the January 2025 Los Angeles fires.",
     "post_url": "https://x.com/HustleBitch_/status/1877770103229485090"},
    {"id": "athens", "kind": "link", "title": "\"Fleeing Israel\" at the airport",
     "blurb": "Crowds said to be fleeing Israel at Ben Gurion airport. Read the signs.",
     "post_url": "https://x.com/butterflyteeee/status/1841592595073405004"},
    {"id": "moscow", "kind": "link", "title": "Moscow in the dark",
     "blurb": "A city without power, shared as Moscow under sanctions in August 2024.",
     "post_url": "https://x.com/jurgen_nauditt/status/1826463362328199217"},
    {"id": "pope", "kind": "link", "title": "The Pope's \"last address\"",
     "blurb": "Shared as Pope Francis's last public words, about Gaza, at Easter 2025.",
     "post_url": "https://x.com/AyshaSusmaz/status/1914305735871115479"},
    {"id": "embassy", "kind": "link", "title": "\"Raid on an embassy in Tehran\"",
     "blurb": "Special forces said to be raiding the Indian embassy in Tehran, May 2024.",
     "post_url": "https://x.com/NavCom24/status/1792246481249833460"},
    {"id": "jakarta", "kind": "link", "title": "Jakarta floods (genuine)",
     "blurb": "A real news post: what Backstory says when the caption is right.",
     "post_url": "https://x.com/jokowi/status/1212554859372670976"},
    {"id": "river", "kind": "link", "title": "Rubbish in a London river",
     "blurb": "A phone video with no earlier copy online: Backstory does not guess.",
     "post_url": "https://x.com/mrsunshinebaby/status/2010783577164653054"},
    {"id": "lahaina", "kind": "photo", "title": "\"This house survived the LA fires\"",
     "blurb": "An uploaded photo with its caption, January 2025.",
     "caption": "This house survived the Los Angeles wildfires while every home around it burned. Unbelievable. #PalisadesFire",
     "posted_on": "2025-01-12", "local_image": "lahaina.jpg"},
    {"id": "morgue", "kind": "photo", "title": "Screenshot: \"hidden flood victims\"",
     "blurb": "A screenshot of a Spanish post; SAM 3.1 cuts the photos out of it.",
     "caption": "Las fotos que no quieren que veas: la morgue con todos los conductores que se llevó el agua por delante en la DANA de Valencia.",
     "posted_on": "2024-12-30", "local_image": "morgue_raw.jpg"},
]


# Cases on public-domain photos (U.S. federal government works on Wikimedia Commons) with captions written for the
# demo. Their photos and recorded answers are committed, so `docker compose up` works offline with no keys.
PUBLIC = [
    {"id": "valencia", "kind": "photo", "title": "\"Valencia today, after the floods\"",
     "blurb": "A staged example: a famous flood photo with a Spanish caption about Valencia, October 2024.",
     "caption": "Así está Valencia hoy después de la DANA. Barrios enteros bajo el agua y nadie dice nada.",
     "posted_on": "2024-10-30", "local_image": "katrina.jpg",
     "credit": "U.S. Coast Guard, Petty Officer 2nd Class Kyle Niemi, 29 Aug 2005, public domain (Wikimedia Commons)"},
    {"id": "katrina_true", "kind": "photo", "title": "The same photo, true caption",
     "blurb": "The caption that matches the photo's history: what \"Fits\" looks like.",
     "caption": "New Orleans under water after Hurricane Katrina, 29 August 2005.",
     "posted_on": "2005-08-30", "local_image": "katrina.jpg",
     "credit": "U.S. Coast Guard, Petty Officer 2nd Class Kyle Niemi, 29 Aug 2005, public domain (Wikimedia Commons)"},
    {"id": "kamchatka", "kind": "photo", "title": "\"Tsunami in Kamchatka this morning\"",
     "blurb": "A staged example: a 2011 photo with a caption about the July 2025 Kamchatka earthquake.",
     "caption": "BREAKING: the tsunami has reached the Kamchatka coast this morning. Whole towns flooded.",
     "posted_on": "2025-07-30", "local_image": "sendai.jpg",
     "credit": "U.S. Navy photo, 12 Mar 2011, public domain (Wikimedia Commons)"},
]


def card_image(post):
    """A still for the example card: the post's first photo, or a frame of its video."""
    if post["photos"]:
        data = post["photos"][0]
    else:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(post["video"])
        data = video.frames(f.name)[0]["jpeg"]
        Path(f.name).unlink(missing_ok=True)
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((640, 640))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/demo")
    ap.add_argument("--local", default="runs/examples_local", help="folder with the uploaded-photo cases' images")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--public", action="store_true", help="build the committed public-domain cases into --out")
    a = ap.parse_args()
    cases = PUBLIC if a.public else DEMOS
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    listed = []
    for d in cases:
        if a.only and d["id"] not in a.only:
            continue
        e = {k: v for k, v in d.items() if k != "local_image"}
        if d["kind"] == "link":
            e["caption"] = d["post_url"].split("//")[1]
            events = pipeline.run(None, "", None, post_url=d["post_url"])
            (out / (d["id"] + ".jpg")).write_bytes(card_image(xpost.read(d["post_url"])))
        else:
            if not a.public:
                shutil.copyfile(Path(a.local) / d["local_image"], out / (d["id"] + ".jpg"))
            events = pipeline.run((Path(a.local) / d["local_image"]).read_bytes(), d["caption"], d["posted_on"])
        e["image"] = d.get("local_image") if a.public else d["id"] + ".jpg"
        result = [ev for ev in events if ev["type"] in ("result", "error")][-1]
        print(d["id"], "->", result.get("verdict") or result.get("text"), "|", (result.get("summary") or "")[:140],
              "| $%.3f" % (result.get("cost") or {}).get("usd", 0), flush=True)
        listed.append(e)
    old = json.loads((out / "examples.json").read_text()) if (out / "examples.json").exists() and a.only else []
    keep = [x for x in old if x["id"] not in {e["id"] for e in listed}]
    order = [d["id"] for d in cases]
    allx = sorted(keep + listed, key=lambda x: order.index(x["id"]) if x["id"] in order else 99)
    (out / "examples.json").write_text(json.dumps(allx, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())

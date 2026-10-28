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
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    listed = []
    for d in DEMOS:
        if a.only and d["id"] not in a.only:
            continue
        e = {k: v for k, v in d.items() if k != "local_image"}
        if d["kind"] == "link":
            e["caption"] = d["post_url"].split("//")[1]
            events = pipeline.run(None, "", None, post_url=d["post_url"])
            (out / (d["id"] + ".jpg")).write_bytes(card_image(xpost.read(d["post_url"])))
        else:
            shutil.copyfile(Path(a.local) / d["local_image"], out / (d["id"] + ".jpg"))
            events = pipeline.run((Path(a.local) / d["local_image"]).read_bytes(), d["caption"], d["posted_on"])
        e["image"] = d["id"] + ".jpg"
        result = [ev for ev in events if ev["type"] in ("result", "error")][-1]
        print(d["id"], "->", result.get("verdict") or result.get("text"), "|", (result.get("summary") or "")[:140],
              "| $%.3f" % (result.get("cost") or {}).get("usd", 0), flush=True)
        listed.append(e)
    old = json.loads((out / "examples.json").read_text()) if (out / "examples.json").exists() and a.only else []
    keep = [x for x in old if x["id"] not in {e["id"] for e in listed}]
    order = [d["id"] for d in DEMOS]
    allx = sorted(keep + listed, key=lambda x: order.index(x["id"]) if x["id"] in order else 99)
    (out / "examples.json").write_text(json.dumps(allx, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())

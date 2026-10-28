"""Test G (docs/TEST_G.md): does cutting the photo out of a post screenshot with SAM 3.1 help reverse image search?

Usage: python -m eval.screenshots --images ../sam-scientist/data/5pils_e_test
Writes runs/test_g.json and runs/test_g_shots/ (screenshots and crops, not committed).
"""
import argparse
import io
import json
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("BACKSTORY_REPLAY_DIR", str(ROOT / "runs" / "replay_g"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from backstory import meta, sam, search  # noqa: E402

NAMES = ["daily.truth.now", "maria_lopez84", "NewsWatcher", "jt_reports", "the.real.feed", "localvoice22"]
TEXTS = ["You won't see this on the news. Share before they delete it.",
         "This is what is happening right now. Unbelievable.",
         "Pray for everyone affected. Look at this.",
         "They told us everything was fine. Here is the truth.",
         "Just received this from a friend who is there. Heartbreaking.",
         "Nobody is talking about this. Why?"]
FONT_FILES = ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size, bold=False):
    for f in FONT_FILES:
        try:
            return ImageFont.truetype(f, size, index=1 if bold and f.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def make_screenshot(photo, k, rng):
    """Generic post layout around the photo. Returns (JPEG bytes, photo box)."""
    W, pad = 1080, 40
    pw = W - 2 * pad
    ph = int(photo.height * pw / photo.width)
    lines = rng.randint(2, 4)
    text_h = 44 * lines
    H = 150 + text_h + 30 + ph + 130
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((pad, 40, pad + 80, 120), fill=(rng.randint(60, 200), rng.randint(60, 200), rng.randint(60, 200)))
    d.text((pad + 100, 48), rng.choice(NAMES), fill=(20, 20, 20), font=font(34, True))
    d.text((pad + 100, 92), "%dh · Public" % rng.randint(1, 23), fill=(110, 110, 110), font=font(26))
    words = (" ".join(rng.choice(TEXTS) for _ in range(lines))).split()
    y, line = 150, ""
    for w in words:
        if d.textlength(line + " " + w, font=font(34)) > pw and line:
            d.text((pad, y), line.strip(), fill=(20, 20, 20), font=font(34))
            y += 44
            line = ""
        line += " " + w
        if y >= 150 + text_h - 44:
            break
    d.text((pad, y), line.strip(), fill=(20, 20, 20), font=font(34))
    top = 150 + text_h + 30
    im.paste(photo.resize((pw, ph)), (pad, top))
    if k % 2 == 0:  # banner across the top of the photo
        bh = int(ph * 0.18)
        size = max(28, int(bh * 0.6))
        while size > 28 and d.textlength("BREAKING: SHARE NOW", font=font(size, True)) > pw - 40:
            size -= 4
        f = font(size, True)
        d.text((pad + 20, top + int(bh * 0.15)), "BREAKING: SHARE NOW", fill="white", font=f,
               stroke_width=4, stroke_fill="black")
    fy = top + ph + 30
    d.line((pad, fy, W - pad, fy), fill=(225, 225, 225), width=2)
    for i, label in enumerate(["%d.%dK" % (rng.randint(1, 99), rng.randint(0, 9)), "%d" % rng.randint(50, 900),
                               "Share"]):
        x = pad + i * 330
        d.ellipse((x, fy + 30, x + 40, fy + 70), outline=(110, 110, 110), width=4)
        d.text((x + 56, fy + 32), label, fill=(80, 80, 80), font=font(30))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return buf.getvalue(), (pad, top, pad + pw, top + ph)


def page_urls(image_bytes):
    pages = search.google_vision(image_bytes)["pages"]
    return [p["url"] for p in pages if p["match"] == "full"], [p["url"] for p in pages]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    out_dir = ROOT / "runs" / "test_g_shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    budget = meta.Budget(cap=0.50)
    rows = []
    for f in sorted(Path(a.images).glob("*.jpg")):
        if len(rows) >= a.n:
            break
        orig = f.read_bytes()
        o_full, o_all = page_urls(orig)
        if not o_full:
            print(f.name, "not eligible (no full match)", flush=True)
            continue
        k = len(rows)
        shot, true_box = make_screenshot(Image.open(io.BytesIO(orig)).convert("RGB"), k, rng)
        (out_dir / ("%03d_shot.jpg" % k)).write_bytes(shot)
        found = sam.boxes(shot, "photo", budget=budget)
        if found:
            x1, y1, x2, y2, c = found[0]
            im = Image.open(io.BytesIO(shot))
            buf = io.BytesIO()
            im.crop((int(x1), int(y1), int(x2), int(y2))).save(buf, format="JPEG", quality=92)
            crop, box_iou = buf.getvalue(), iou(found[0][:4], true_box)
        else:
            crop, box_iou = shot, None
        (out_dir / ("%03d_crop.jpg" % k)).write_bytes(crop)
        s_full, s_all = page_urls(shot)
        m_full, m_all = page_urls(crop)
        o_set = set(o_all)
        row = {"k": k, "file": f.name, "banner": k % 2 == 0, "sam_boxes": len(found),
               "iou": round(box_iou, 3) if box_iou is not None else None,
               "hit_S": bool(o_set & set(s_all)), "hit_M": bool(o_set & set(m_all)), "hit_O": True,
               "full_S": len(s_full), "full_M": len(m_full), "full_O": len(o_full)}
        rows.append(row)
        print(k, f.name, "iou", row["iou"], "| hit S", row["hit_S"], "M", row["hit_M"],
              "| full S/M/O", row["full_S"], row["full_M"], row["full_O"], "| sam $%.3f" % budget.usd, flush=True)
        json.dump(rows, open(ROOT / "runs" / "test_g.json", "w"), indent=1)

    n = len(rows)

    def rate(key, sub=rows):
        return round(sum(r[key] for r in sub) / len(sub), 3) if sub else None
    res = {"n": n, "hit_S": rate("hit_S"), "hit_M": rate("hit_M"), "hit_O": 1.0,
           "iou_ge_0_9": round(sum(1 for r in rows if (r["iou"] or 0) >= 0.9) / n, 3) if n else None,
           "sam_no_box": sum(1 for r in rows if not r["sam_boxes"]),
           "mean_full": {a: round(sum(r["full_" + a] for r in rows) / n, 2) for a in "SMO"} if n else None,
           "plain": {"hit_S": rate("hit_S", [r for r in rows if not r["banner"]]),
                     "hit_M": rate("hit_M", [r for r in rows if not r["banner"]])},
           "banner": {"hit_S": rate("hit_S", [r for r in rows if r["banner"]]),
                      "hit_M": rate("hit_M", [r for r in rows if r["banner"]])},
           "sam_usd": round(budget.usd, 3)}
    go = res["hit_M"] >= res["hit_S"] + 0.15 and res["hit_M"] >= 0.8
    nogo = res["hit_M"] <= res["hit_S"] + 0.05
    res["decision"] = "GO" if go and not nogo else "NO-GO" if nogo else "UNCLEAR"
    print(json.dumps(res, indent=1))
    json.dump({"rows": rows, "result": res}, open(ROOT / "runs" / "test_g.json", "w"), indent=1)


if __name__ == "__main__":
    main()

"""Scene witness (Muse Spark watches the whole video or looks at the photo; Muse Wonder checks what it read).

Reverse image search often finds nothing for a phone video. But the footage itself can say where it was filmed:
a shop sign, a banner, a street name, an airport's welcome sign. Spark lists only what can be read or recognised,
each with the second it appears, and picks the most distinctive moments, which are then searched as well.

What it reads is a lead, not proof. A text counts against the caption only when Wonder, looking at that exact frame,
confirms the text is there word for word, that it is part of the filmed scene (not a caption or watermark added by
whoever shared it), that the place it names lies in another country than the caption claims, and that the text could
not plausibly be seen at the claimed place (flags, placards, adverts, chain stores and departure boards can).
"""
import subprocess
import tempfile
from pathlib import Path

from . import config, meta, replay, video

MAX_SECONDS = 60
MAX_MOMENTS = 3

LOOK = """Watch this {what}. List only what a person could check by looking at it:
- every piece of readable text that is part of the filmed scene (shop signs, street names, banners, notices,
  vehicle markings, licence plates), quoted exactly, with the second it is clearest;
- text added on top of the footage (captions, channel logos, watermarks, usernames) separately, as overlays;
- recognisable landmarks, with the second they are clearest.
Do not guess: if a text is too blurry to read in full, leave it out. Do not use the post's caption, you have not
seen it. Also give up to 3 moments (seconds) that best identify this footage: sharp, distinctive, no big overlay.

Reply with one JSON object:
{{"scene_texts": [{{"t": seconds, "text": "exact text", "names_place": "the city/region/country this text names or
   clearly belongs to, or null"}}],
  "overlays": [{{"t": seconds, "text": "exact text"}}],
  "landmarks": [{{"t": seconds, "name": "landmark", "place": "city, country"}}],
  "moments": [seconds],
  "place_from_scene": "where the readable texts and landmarks place the scene, or null"}}"""

CHECK = """This is one frame from a video (second {t}). Someone reading the video said this text is visible in the
filmed scene: "{text}", and that it points to: {place}.
The video's caption claims the scene is in: {claimed}.

Look at the frame yourself and answer:
1. Is this exact text visible in the frame (allow small differences in case and punctuation)?
2. Is it part of the filmed scene (a physical sign, banner, vehicle, building), not text added on top of the footage?
3. Does it name or clearly belong to a specific place, and which country is that?
4. Is that country different from the country of the claimed place?
5. Could this text still plausibly be seen at the claimed place? It could if it is a flag, a banner or placard
   carried by people, an advert, a chain store or brand, a destination or departure board, a vehicle from
   elsewhere, a place inside or bordering the claimed place (Vatican City in Rome, a border town), or a name
   that exists in several countries. Only a fixed sign that belongs to the place where it stands (a city's
   welcome sign, a street name, a local shop or institution with its town) rules the claimed place out.

Reply with one JSON object:
{{"visible": true | false, "in_scene": true | false, "country": "country the text points to, or null",
  "claimed_country": "country of the claimed place, or null", "other_country": true | false,
  "could_be_at_claimed_place": true | false, "reason": "one short sentence"}}"""


def small_video(path):
    """The first MAX_SECONDS of the video at 720p, 2 frames per second, no sound: what the model watches.
    Recorded by the source file's hash so a different ffmpeg build does not change the request."""
    def make():
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(MAX_SECONDS), "-vf",
                            "scale=-2:'min(720,ih)'", "-r", "2", "-an", "-c:v", "libx264", "-crf", "30", "-y",
                            str(out)], capture_output=True, timeout=180)
            return out.read_bytes() if out.exists() else None
    return replay.cached_bytes("witnessvid", {"video_sha256": video.file_sha(path), "s": MAX_SECONDS}, make)


def _num(v):
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return None


def look(video_path=None, image_bytes=None, budget=None):
    """What the footage itself shows: {'scene_texts', 'overlays', 'landmarks', 'moments', 'place_from_scene'}."""
    kw = {}
    if video_path:
        clip = small_video(video_path)
        if not clip:
            return None
        kw["video_mp4"], what = clip, "video"
    else:
        kw["image_bytes"], what = image_bytes, "photo"
    try:
        out, _ = meta.ask_json(config.SPARK, LOOK.format(what=what), effort="medium", budget=budget,
                               note="witness", **kw)
    except ValueError:
        return None
    texts = [x for x in out.get("scene_texts") or [] if isinstance(x, dict) and str(x.get("text") or "").strip()]
    for x in texts:
        x["t"] = _num(x.get("t")) or 0.0
        x["text"] = str(x["text"]).strip()[:200]
    moments = [m for m in (_num(v) for v in out.get("moments") or []) if m is not None][:MAX_MOMENTS]
    return {"scene_texts": texts, "overlays": out.get("overlays") or [], "landmarks": out.get("landmarks") or [],
            "moments": moments, "place_from_scene": out.get("place_from_scene")}


def check(claim, seen, frame_at, budget=None):
    """Wonder checks each scene text that names a place, on its own frame. Returns the confirmed ones:
    [{'t', 'text', 'country', 'claimed_country', 'other_country', 'reason', 'jpeg'}]."""
    if not seen or not claim.get("place"):
        return []
    out = []
    for x in [x for x in seen["scene_texts"] if x.get("names_place")][:4]:
        jpeg = frame_at(x["t"])
        if not jpeg:
            continue
        try:
            v, _ = meta.ask_json(config.WONDER, CHECK.format(t=x["t"], text=x["text"], place=x["names_place"],
                                                             claimed=claim["place"]),
                                 image_bytes=jpeg, effort="medium", budget=budget, note="witness check")
        except ValueError:
            continue
        ok = all(meta.truthy(v.get(k)) for k in ("visible", "in_scene"))
        out.append({"t": x["t"], "text": x["text"], "country": v.get("country"),
                    "claimed_country": v.get("claimed_country"), "other_country": ok and meta.truthy(v.get("other_country"))
                    and v.get("could_be_at_claimed_place") is False,
                    "confirmed": ok, "reason": v.get("reason"), "jpeg": jpeg})
    return out

"""The decision: a fixed date rule, a judge (Muse Spark) and a critic (Muse Wonder) that can send the judge back.

1. Date rule (code, no model): if an archived copy of the image file is more than a day older than the earliest
   date the caption allows, the caption cannot be right. This rule alone was tested on 105 real cases
   (docs/TESTS.md): it caught 49% of false captions with 1% false alarms.
2. Judge (Spark): sees the photo, the claim and the evidence table, and gives a verdict that must cite evidence.
3. Critic (Wonder): checks that the cited evidence really supports the verdict. If not, the judge gets one more
   try with the critic's objection; if the critic still disagrees, the answer is "cannot_tell".
4. Grounds check (code, no model): an approved "inconsistent" must rest on evidence the code can verify in the
   table, or it becomes "cannot_tell". The models propose; the code decides what counts as proof.
"""
import datetime as dt
import json
import re

from . import config, matcher, meta, search

VERDICTS = ("consistent", "inconsistent", "cannot_tell")


def date_rule(claim, evidence):
    start = claim.get("period_start")
    if not start:
        return None
    start = dt.date.fromisoformat(start)
    best = None
    for e in evidence:
        if e.get("match") not in ("full", "partial"):
            continue  # the rule was tested on exact search matches only; look-alikes go to the judge
        if e.get("image_first") and dt.date.fromisoformat(e["image_first"]) < start - dt.timedelta(days=1):
            if best is None or e["image_first"] < best["image_first"]:
                best = e
    if not best:
        return None
    days = (start - dt.date.fromisoformat(best["image_first"])).days
    return {"evidence_id": best["id"], "image_first": best["image_first"], "period_start": start.isoformat(),
            "days_before": days, "snapshot": best.get("image_snapshot")}


# Dates on the web are noisy by days (time zones, updated pages, "yesterday" in captions); a copy only a few days
# older than the claim is not proof that the caption is wrong.
MARGIN_DAYS = 7


def _first_dated(e):
    """Earliest date the table proves this exact image existed: the archived image file, or the publication date
    of a page that shows the same image file. A page's own archive date is not used: the page may predate the photo."""
    dates = [e.get("image_first")]
    if e.get("match") == "full" or (e.get("match") == "confirmed look-alike" and e.get("page_published")):
        dates.append(_iso_day(e.get("page_published")))
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def _iso_day(value):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or ""))
    return m.group(1) if m else None


GENERIC = set("city town region state county district province united states kingdom republic near north south east "
              "west central island islands area".split())


def _place_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", str(text or "").lower())} - GENERIC


def _same_place(a, b):
    return bool(_place_words(a) & _place_words(b))


def _dated_before(described, start):
    if not described or not start:
        return False
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(described))
    if not m:
        return False
    y, mo, d = int(m.group(1)), int(m.group(2) or 12), int(m.group(3) or 28)
    try:
        return dt.date(y, mo, d) < dt.date.fromisoformat(start) - dt.timedelta(days=MARGIN_DAYS)
    except ValueError:
        return False


def grounds(claim, evidence, judged):
    """Check an "inconsistent" verdict against the table. Returns {"ok", "kind", "ids", "text"}.

    It passes if a cited copy of the same image is dated more than MARGIN_DAYS before the earliest date the caption
    allows, or if at least two cited pages on different sites (not fact-checkers) show the same image file and
    describe where, when or what it is (the judge has said how that differs from the caption)."""
    by_id = {e["id"]: e for e in evidence}
    cited = [by_id[i] for i in (judged.get("cited") or []) if i in by_id]
    start = claim.get("period_start")
    if start:
        limit = (dt.date.fromisoformat(start) - dt.timedelta(days=MARGIN_DAYS)).isoformat()
        early = [e for e in cited if e.get("match") in ("full", "confirmed look-alike")
                 and _first_dated(e) and _first_dated(e) < limit]
        if early:
            e = min(early, key=_first_dated)
            return {"ok": True, "kind": "earlier copy", "ids": [x["id"] for x in early],
                    "text": "%s (%s) shows this image by %s, more than %d days before %s"
                            % (e["id"], e["domain"], _first_dated(e), MARGIN_DAYS, start)}
    # Social and video sites carry what users wrote, not an editor's description, so they do not count here.
    origin = [e for e in cited if e.get("match") in ("full", "confirmed look-alike") and not e.get("fact_checker")
              and not search.low_value("https://" + e["domain"])
              and (e.get("described_place") or e.get("described_event") or e.get("described_date"))]
    # Pages that put the image in the claimed place and do not date it earlier only disagree on details of the
    # event ("a mosque" vs "the palace" in the same city on the same day): that is not proof.
    claimed_place = claim.get("place")
    differ = [e for e in origin if not (claimed_place and _same_place(e.get("described_place"), claimed_place)
                                        and not _dated_before(e.get("described_date"), start))]
    sites = sorted({e["domain"] for e in differ})
    origin = differ
    if len(sites) >= 2:
        return {"ok": True, "kind": "independent descriptions", "ids": [e["id"] for e in origin],
                "text": "%d sites describe this image differently from the caption: %s" % (len(sites), ", ".join(sites))}
    return {"ok": False, "kind": None, "ids": [],
            "text": "no cited copy is dated more than %d days before the claim, and fewer than two independent "
                    "sites describe the image" % MARGIN_DAYS}


def evidence_table(evidence):
    rows = []
    for e in evidence:
        rows.append({k: e.get(k) for k in ("id", "domain", "match", "match_reason", "image_first", "page_first",
                                            "page_published",
                                            "described_place", "described_date", "described_event", "quote",
                                            "fact_checker")})
    return json.dumps(rows, ensure_ascii=False, indent=0)


JUDGE = """You check whether a caption fits a photo, using evidence of where this exact photo appeared online before.

Claim made by the caption (as extracted): place: {place}; event: {event}; date: {claimed_date};
earliest possible date of the claimed scene: {start}.
Original caption: "{caption}"

Evidence table (one row per web page where reverse image search found this photo):
- image_first / page_first: first Internet Archive capture of the image file / page. This proves it existed BY that
  date. A late or missing capture proves nothing: the Archive often captures files years after they appear.
- page_published: publication date from the page's own metadata (usually reliable, but a page can be updated later)
- described_*: how that page describes the photo
- match: "full" = the same image file; "partial" = only part of the image matches (may be a crop or a similar photo);
  "confirmed look-alike" = found as visually similar, then a separate checker compared it with the post's image and
  confirmed with high confidence that both come from the same photo or video footage (match_reason says why).
  Treat a confirmed look-alike as the same source, so its archive date counts like any other copy.
- fact_checker: true if the page is a fact-checking site
{table}

Rules:
- A photo that was online before the claimed event cannot show that event.
- A page that describes the same photo as a different place or event is evidence against the caption, stronger
  if the page was published before the claimed date.
- Pages that simply repeat the caption are not independent confirmation.
- If the evidence does not settle it, the answer is "cannot_tell". Never guess from the picture alone.
- What counts as proof for "inconsistent" (code checks it afterwards; cite every row it rests on):
  a copy of the same image dated more than a week before the earliest possible date (a few days earlier is not
  proof: web dates are noisy), or at least two pages on different sites that show the same image and describe a
  different place, date or event. One page with a different description is a sign, not proof: say "cannot_tell".
- A caption about several images, or a date given only as "published"/"found" rather than when the photo was taken,
  is vague; do not treat an older copy as proof against a date that only says when the image was found.
{critic_note}
Reply with one JSON object:
{{"verdict": "consistent" | "inconsistent" | "cannot_tell",
  "cited": ["evidence ids that support the verdict"],
  "summary": "one or two plain sentences for a reader, naming the decisive evidence and its date",
  "actual": {{"place": "where the photo was really taken, per the earliest full-match source (the original publisher
              rather than later reposts or partial matches), or null",
              "date": "when, or null", "event": "what it really shows, or null"}}}}"""


CRITIC = """You are the critic in a fact-checking team. A judge decided whether a caption fits a photo. Check the
judge's work against the evidence. Do not redo the case from your own knowledge; check the reasoning.

Claim: place: {place}; event: {event}; date: {claimed_date}; earliest possible date: {start}.
Evidence table (image_first / page_first = first Internet Archive capture, which proves the file or page existed BY
that date; a late or missing capture proves nothing; page_published = date from the page's own metadata):
{table}
match: "full" / "partial" = exact search matches; "confirmed look-alike" = an image the search called visually
similar and a separate checker judged to come from the same photo or footage.
{look_alikes}
Judge's answer:
{judge}

Approve only if all hold:
1. Every cited evidence id exists and says what the judge claims (dates and descriptions match the table).
2. "inconsistent" rests on at least one concrete item: an archive or publication date before the earliest possible
   date, or a page describing this photo as a different place or event. Disagreement on unimportant detail is not enough.
   A publication date from an established news or agency page counts as evidence even when the Archive captured the
   page later (a late capture proves nothing); be wary of it only on sites that repost or aggregate content.
   If pages disagree about where or when the photo was really taken but every version predates the claimed date,
   that does not weaken "inconsistent": the caption is wrong either way.
3. "consistent" rests on independent evidence that matches place and date, not on pages repeating the caption.
4. "cannot_tell" is acceptable whenever the evidence is thin.
5. If the verdict rests on a confirmed look-alike, you must check the images yourself: they must show the same
   moment from the same photo or footage, not just a similar scene. If they do, its archive date counts like any copy.
Reply with one JSON object:
{{"approve": true | false, "same_source_checked": "for each cited look-alike: id and same / different, or null",
  "problem": "what is wrong, one sentence, or null"}}"""


def _fmt(claim):
    return {"place": claim.get("place"), "event": claim.get("event"), "claimed_date": claim.get("claimed_date"),
            "start": claim.get("period_start") or "unknown", "caption": claim.get("caption", "")}


def judge(image_bytes, claim, evidence, critic_note=None, budget=None):
    note = ("\nA critic rejected your previous answer: %s\nTake this into account." % critic_note) if critic_note else ""
    try:
        out, _ = meta.ask_json(config.SPARK, JUDGE.format(table=evidence_table(evidence), critic_note=note,
                                                          **_fmt(claim)),
                               image_bytes=image_bytes, budget=budget, note="judge")
    except ValueError:
        out = {"verdict": "cannot_tell", "summary": "The judge gave no usable answer, so there is no verdict."}
    return _clean_judgement(out, {e["id"] for e in evidence})


def _clean_judgement(out, ids):
    """Model output in the shape the rest of the code expects, whatever the model returned."""
    if out.get("verdict") not in VERDICTS:
        out["verdict"] = "cannot_tell"
    cited = out.get("cited")
    if isinstance(cited, str):
        cited = re.findall(r"E\d+", cited)
    out["cited"] = [str(x) for x in (cited if isinstance(cited, list) else []) if str(x) in ids]
    out["summary"] = str(out.get("summary") or "").strip()
    actual = out.get("actual") if isinstance(out.get("actual"), dict) else {}
    out["actual"] = {k: (str(actual[k]) if actual.get(k) not in (None, "", "null") else None)
                     for k in ("place", "date", "event")}
    return out


def critic(claim, evidence, judged, post_image=None, budget=None):
    j = {k: judged.get(k) for k in ("verdict", "cited", "summary", "actual")}
    # Cited look-alikes are shown to the critic next to the post's image, so it checks the match itself.
    cited = set(judged.get("cited") or [])
    shown, images = [], []
    for e in evidence:
        if e["id"] in cited and e.get("match") == "confirmed look-alike" and post_image is not None and len(shown) < 2:
            cand = matcher.download(e["url"])
            if cand is not None:
                shown.append(e["id"])
                images.append(cand)
    look = ""
    if shown:
        images = [post_image] + images
        look = ("Image 1 is the post's image. " + " ".join("Image %d is evidence %s." % (i + 2, eid)
                                                        for i, eid in enumerate(shown)) + "\n")
    try:
        out, _ = meta.ask_json(config.WONDER, CRITIC.format(table=evidence_table(evidence), look_alikes=look,
                                                            judge=json.dumps(j, ensure_ascii=False), **_fmt(claim)),
                               images=images or None, effort="medium", budget=budget, note="critic")
    except ValueError:
        out = {"approve": False, "problem": "the critic gave no usable answer"}
    out["approve"] = meta.truthy(out.get("approve"))
    return out

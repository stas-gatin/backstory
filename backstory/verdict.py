"""The decision: a fixed date rule, a judge (Muse Spark) and a critic (Muse Wonder) that can send the judge back.

1. Date rule (code, no model): if an archived copy of the image file is more than a day older than the earliest
   date the caption allows, the caption cannot be right. This rule alone was tested on 105 real cases
   (docs/TESTS.md): it caught 49% of false captions with 1% false alarms.
2. Judge (Spark): sees the photo, the claim and the evidence table, and gives a verdict that must cite evidence.
3. Critic (Wonder): checks that the cited evidence really supports the verdict. If not, the judge gets one more
   try with the critic's objection; if the critic still disagrees, the answer is "cannot_tell".
"""
import datetime as dt
import json

from . import config, meta

VERDICTS = ("consistent", "inconsistent", "cannot_tell")


def date_rule(claim, evidence):
    start = claim.get("period_start")
    if not start:
        return None
    start = dt.date.fromisoformat(start)
    best = None
    for e in evidence:
        if e.get("image_first") and dt.date.fromisoformat(e["image_first"]) < start - dt.timedelta(days=1):
            if best is None or e["image_first"] < best["image_first"]:
                best = e
    if not best:
        return None
    days = (start - dt.date.fromisoformat(best["image_first"])).days
    return {"evidence_id": best["id"], "image_first": best["image_first"], "period_start": start.isoformat(),
            "days_before": days, "snapshot": best.get("image_snapshot")}


def evidence_table(evidence):
    rows = []
    for e in evidence:
        rows.append({k: e.get(k) for k in ("id", "domain", "match", "image_first", "page_first", "page_published",
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
- match: "full" = the same image file; "partial" = only part of the image matches (may be a crop or a similar photo)
- fact_checker: true if the page is a fact-checking site
{table}

Rules:
- A photo that was online before the claimed event cannot show that event.
- A page that describes the same photo as a different place or event is evidence against the caption, stronger
  if the page was published before the claimed date.
- Pages that simply repeat the caption are not independent confirmation.
- If the evidence does not settle it, the answer is "cannot_tell". Never guess from the picture alone.
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
Reply with one JSON object:
{{"approve": true | false, "problem": "what is wrong, one sentence, or null"}}"""


def _fmt(claim):
    return {"place": claim.get("place"), "event": claim.get("event"), "claimed_date": claim.get("claimed_date"),
            "start": claim.get("period_start") or "unknown", "caption": claim.get("caption", "")}


def judge(image_bytes, claim, evidence, critic_note=None, budget=None):
    note = ("\nA critic rejected your previous answer: %s\nTake this into account." % critic_note) if critic_note else ""
    out, _ = meta.ask_json(config.SPARK, JUDGE.format(table=evidence_table(evidence), critic_note=note, **_fmt(claim)),
                           image_bytes=image_bytes, budget=budget, note="judge")
    if out.get("verdict") not in VERDICTS:
        out["verdict"] = "cannot_tell"
    return out


def critic(claim, evidence, judged, budget=None):
    j = {k: judged.get(k) for k in ("verdict", "cited", "summary", "actual")}
    out, _ = meta.ask_json(config.WONDER, CRITIC.format(table=evidence_table(evidence),
                                                        judge=json.dumps(j, ensure_ascii=False), **_fmt(claim)),
                           effort="medium", budget=budget, note="critic")
    out["approve"] = bool(out.get("approve"))
    return out

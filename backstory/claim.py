"""Agent 1, the claim reader (Muse Spark with web search).

Turns a caption in any language into what it asserts: place, event, and the date the photo supposedly shows.
Named events and relative dates ("yesterday", "the DANA floods") are resolved with web search, so the claim gets
a concrete earliest date. It never looks at the photo: its job is what the caption says, not whether it is true.
"""
import datetime as dt

from . import config, meta

# A post that presents media as news ("breaking", "just landed", "first picture of") and gives no other date
# implies the scene is recent. It is taken as no older than this many days before the post: anything shown to
# exist earlier than that (plus the usual margin) cannot be the news the post presents.
IMPLIED_DAYS = 30

PROMPT = """You read the caption of a photo shared online and extract what it claims. Do not judge whether it is true.

Caption: "{caption}"
The post was published on: {posted_on}

If the caption names an event (a flood, a protest, a match) or uses a relative date ("yesterday", "this morning"),
use web search to find when that event happened, so the claim gets a concrete date. Search only for the event,
never for this photo or for fact-checks of it.

Reply with one JSON object:
{{"place": "city, region, country as claimed (English), or null",
  "event": "what the photo supposedly shows, in English, short, or null if the caption does not say",
  "claimed_date": "the date or period as claimed, in words",
  "period_start": "YYYY-MM-DD: the earliest day the claimed scene can have happened, or null if the caption gives no time at all",
  "precision": "day" | "month" | "year" | "none",
  "date_basis": "how you got period_start, one short sentence (e.g. 'caption says yesterday; post published 2024-10-30')",
  "presented_as_new": true if the caption presents the photo as showing something that is happening now or just
    happened (news, "breaking", "just", "now", "tonight", "first picture of", an ongoing event told in the present
    tense), false if it is presented as old, as an illustration, or the caption does not say,
  "language": "language of the caption"}}"""


def read_claim(caption, posted_on=None, budget=None):
    # Never today's date: it would change the request every day and break recorded checks.
    posted_on = posted_on or "unknown"
    try:
        data, sources = meta.ask_json(config.SPARK, PROMPT.format(caption=caption.strip(), posted_on=posted_on),
                                      web_search=True, budget=budget, note="claim")
    except ValueError:
        data, sources = {}, []
    start = data.get("period_start")
    try:
        data["period_start"] = dt.date.fromisoformat(str(start)).isoformat() if start else None
    except ValueError:
        data["period_start"] = None
    data["implied"] = False
    if not data["period_start"] and data.get("presented_as_new") is True and posted_on != "unknown":
        try:
            posted = dt.date.fromisoformat(posted_on[:10])
        except ValueError:
            posted = None
        if posted:
            data["period_start"] = (posted - dt.timedelta(days=IMPLIED_DAYS)).isoformat()
            data["precision"] = "implied"
            data["implied"] = True
            data["date_basis"] = ("no date in the caption, but it presents the media as news on %s, so the scene is "
                                  "taken as no older than %d days before" % (posted.isoformat(), IMPLIED_DAYS))
            if not data.get("claimed_date"):
                data["claimed_date"] = "recent, as of the post on %s" % posted.isoformat()
    for k in ("place", "event", "claimed_date"):
        data[k] = str(data[k]) if data.get(k) not in (None, "", "null") else None
    data["sources"] = [s for s in sources if s.get("cited")][:5]
    data["caption"] = caption.strip()
    data["posted_on"] = posted_on
    return data

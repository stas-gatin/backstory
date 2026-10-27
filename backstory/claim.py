"""Agent 1, the claim reader (Muse Spark with web search).

Turns a caption in any language into what it asserts: place, event, and the date the photo supposedly shows.
Named events and relative dates ("yesterday", "the DANA floods") are resolved with web search, so the claim gets
a concrete earliest date. It never looks at the photo: its job is what the caption says, not whether it is true.
"""
import datetime as dt

from . import config, meta

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
    for k in ("place", "event", "claimed_date"):
        data[k] = str(data[k]) if data.get(k) not in (None, "", "null") else None
    data["sources"] = [s for s in sources if s.get("cited")][:5]
    data["caption"] = caption.strip()
    data["posted_on"] = posted_on
    return data

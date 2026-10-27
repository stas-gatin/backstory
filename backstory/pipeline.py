"""Runs one check and yields progress events, so the web page can show each agent at work.

Event types: "step" (an agent starts or finishes), "evidence" (one row of the evidence table is ready),
"result" (the final answer) and "error".
"""
import concurrent.futures as cf

from . import archive, claim, config, meta, reader, replay, search, verdict

AGENTS = {
    "claim": "Claim reader · Muse Spark + web search",
    "search": "Image search · Google Vision",
    "archive": "Archivist · Internet Archive",
    "reader": "Page reader · Muse Spark",
    "rule": "Date rule · code",
    "judge": "Judge · Muse Spark",
    "critic": "Critic · Muse Wonder",
}


def step(agent, status, text, **data):
    return {"type": "step", "agent": agent, "label": AGENTS[agent], "status": status, "text": text, **data}


def _min_date(*dates):
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def run(image_bytes, caption, posted_on=None, matches=None, exclude_fact_checkers=False):
    """matches: a fixed search result (evaluation); None means live reverse image search."""
    budget = meta.Budget()
    try:
        yield from _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget)
    except replay.NotInReplay as e:
        yield {"type": "error", "text": "This check was not recorded, and the demo runs without keys (replay mode). "
                                        "Pick one of the examples, or run Backstory locally with keys. (%s)" % e}
    except search.SearchUnavailable as e:
        yield {"type": "error", "text": str(e)}
    except meta.BudgetExceeded as e:
        yield {"type": "error", "text": "Stopped: %s." % e}
    except Exception as e:  # noqa: BLE001 - reported to the page, never swallowed silently
        yield {"type": "error", "text": "%s: %s" % (type(e).__name__, e)}


def _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget):
    # 1. What does the caption claim?
    yield step("claim", "running", "Reading the caption")
    c = claim.read_claim(caption, posted_on, budget=budget)
    yield step("claim", "done", "Claims: %s · %s · %s" % (c.get("event") or "?", c.get("place") or "?",
                                                         c.get("claimed_date") or "no date"),
               claim=c)

    # 2. Where else is this photo online?
    yield step("search", "running", "Searching the web for this exact photo")
    found = search.from_list(matches) if matches is not None else search.google_vision(image_bytes)
    pages = []
    for p in found["pages"]:
        fc = search.is_fact_checker(p["url"])
        if fc and exclude_fact_checkers:
            continue
        if p["url"] not in [q["url"] for q in pages]:
            pages.append(dict(p, fact_checker=fc, domain=search.domain(p["url"])))
    yield step("search", "done", "Found the photo on %d page%s" % (len(pages), "" if len(pages) == 1 else "s"),
               count=len(pages))
    if not pages:
        yield from _finish(c, [], None, None, None, budget, "No earlier copy of this photo was found online, "
                                                            "so there is nothing to check the caption against.")
        return

    # 3 + 4. Archive dates and page reading, in parallel.
    to_read = pages[:config.MAX_PAGES]
    image_jobs, n = [], 0
    for i, p in enumerate(pages):
        for u in p.get("image_urls", [])[:3]:
            if n < config.MAX_ARCHIVE_LOOKUPS:
                image_jobs.append((i, u))
                n += 1
    ev = [{"id": "E%d" % (i + 1), "url": p["url"], "domain": p["domain"], "fact_checker": p["fact_checker"],
           "match": p.get("match"), "image_first": None, "image_snapshot": None, "page_first": None}
          for i, p in enumerate(pages)]
    yield step("archive", "running", "Looking up first archive dates for %d image files and %d pages"
               % (len(image_jobs), len(to_read)))
    yield step("reader", "running", "Opening %d pages to see how they describe the photo" % len(to_read))
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        futs = {}
        for i, p in enumerate(to_read):
            futs[pool.submit(reader.read_page, p["url"], p.get("image_urls", []), budget)] = ("read", i, None)
            futs[pool.submit(archive.first_capture, p["url"])] = ("page", i, None)
        for i, u in image_jobs:
            futs[pool.submit(archive.first_capture, u)] = ("image", i, u)
        for f in cf.as_completed(futs):
            kind, i, _ = futs[f]
            res = f.result()
            e = ev[i]
            if kind == "read":
                e.update(opened=res.get("opened"), title=res.get("title"), page_published=res.get("page_date"),
                         described_place=res.get("place"), described_date=res.get("date"),
                         described_event=res.get("event"), quote=res.get("quote"), relevant=res.get("relevant"))
            elif kind == "page":
                e["page_first"] = res["date"]
                e["page_snapshot"] = res["snapshot"]
            elif res["date"] and (not e["image_first"] or res["date"] < e["image_first"]):
                e["image_first"], e["image_snapshot"] = res["date"], res["snapshot"]
            yield {"type": "evidence", "row": e}
    useful = [e for i, e in enumerate(ev) if i < len(to_read) or e["image_first"]]
    dated = sum(1 for e in useful if e["image_first"] or e["page_first"])
    yield step("archive", "done", "%d of %d pages have an archive date" % (dated, len(useful)))
    yield step("reader", "done", "%d pages describe the photo" % sum(1 for e in useful if e.get("relevant")))

    # 5. Fixed date rule.
    rule = verdict.date_rule(c, useful)
    if rule:
        yield step("rule", "done", "The image file was archived on %s, %d days before the earliest date the caption "
                                   "allows (%s)" % (rule["image_first"], rule["days_before"], rule["period_start"]),
                   fired=True, rule=rule)
    else:
        yield step("rule", "done", "No archived copy older than the claimed date", fired=False)

    # 6. Judge and critic, with one send-back.
    yield step("judge", "running", "Weighing the evidence")
    j = verdict.judge(image_bytes, c, useful, budget=budget)
    yield step("judge", "done", "%s: %s" % (j["verdict"], j.get("summary", "")), judged=j)
    yield step("critic", "running", "Checking the judge's reasoning against the evidence")
    cr = verdict.critic(c, useful, j, budget=budget)
    if not cr["approve"]:
        yield step("critic", "done", "Sent back: %s" % cr.get("problem"), critic=cr, approve=False)
        yield step("judge", "running", "Second attempt after the critic's objection")
        j = verdict.judge(image_bytes, c, useful, critic_note=cr.get("problem"), budget=budget)
        yield step("judge", "done", "%s: %s" % (j["verdict"], j.get("summary", "")), judged=j)
        yield step("critic", "running", "Checking the second attempt")
        cr = verdict.critic(c, useful, j, budget=budget)
    yield step("critic", "done", "Approved" if cr["approve"] else "Still rejected: %s" % cr.get("problem"),
               critic=cr, approve=cr["approve"])
    yield from _finish(c, useful, rule, j, cr, budget)


def _finish(c, evidence, rule, judged, crit, budget, empty_reason=None):
    if rule:
        final, basis = "inconsistent", "date rule"
        summary = (judged or {}).get("summary") if (judged or {}).get("verdict") == "inconsistent" else None
        summary = summary or ("An archived copy of this image file is dated %s, %d days before the earliest date "
                              "the caption allows." % (rule["image_first"], rule["days_before"]))
    elif judged and crit and crit["approve"]:
        final, basis, summary = judged["verdict"], "judge, approved by critic", judged.get("summary")
    elif judged:
        final, basis = "cannot_tell", "judge and critic disagree"
        summary = "The evidence does not settle it: %s" % (crit.get("problem") or "the critic rejected the reasoning.")
    else:
        final, basis, summary = "cannot_tell", "no evidence", empty_reason

    timeline = []
    if c.get("period_start"):
        timeline.append({"date": c["period_start"], "kind": "claim",
                         "text": "Earliest date the caption allows (%s)" % (c.get("claimed_date") or "")})
    for e in evidence:
        first = _min_date(e.get("image_first"), e.get("page_first"))
        if first:
            what = "image file archived" if first == e.get("image_first") else "page archived"
            timeline.append({"date": first, "kind": "evidence", "id": e["id"],
                             "text": "%s: %s" % (e["domain"], what),
                             "url": e.get("image_snapshot") if what.startswith("image") else e.get("page_snapshot")})
    timeline.sort(key=lambda t: t["date"])
    cited = set((judged or {}).get("cited") or [])
    if rule:
        cited.add(rule["evidence_id"])
    yield {"type": "result", "verdict": final, "basis": basis, "summary": summary, "claim": c,
           "actual": (judged or {}).get("actual"), "rule": rule, "cited": sorted(cited), "evidence": evidence,
           "timeline": timeline, "critic": crit, "cost": budget.summary(), "mode": config.MODE}

"""Runs one check and yields progress events, so the web page can show each agent at work.

Event types: "step" (an agent starts or finishes), "evidence" (one row of the evidence table is ready),
"result" (the final answer) and "error".
"""
import base64
import concurrent.futures as cf
import io
import re

from PIL import Image

from . import archive, claim, config, matcher, meta, reader, replay, sam, search, verdict, video

AGENTS = {
    "frames": "Frame grabber · ffmpeg",
    "speech": "Speech reader · Muse Voice Transcribe",
    "claim": "Claim reader · Muse Spark + web search",
    "cutout": "Photo finder · SAM 3.1",
    "search": "Image search · Google Vision",
    "match": "Match checker · Muse Spark",
    "archive": "Archivist · Internet Archive",
    "reader": "Page reader · Muse Spark",
    "rule": "Date rule · code",
    "judge": "Judge · Muse Spark",
    "critic": "Critic · Muse Wonder",
}


WORDS = {"inconsistent": "Does not fit", "consistent": "Fits", "cannot_tell": "Cannot verify"}
ISO = re.compile(r"^\d{4}(-\d\d){0,2}$")


def step(agent, status, text, **data):
    return {"type": "step", "agent": agent, "label": AGENTS[agent], "status": status, "text": text, **data}


def _thumb(jpeg, side=160):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _count(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def _min_date(*dates):
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def run(image_bytes, caption, posted_on=None, matches=None, exclude_fact_checkers=False, video_path=None):
    """matches: a fixed search result (evaluation); None means live reverse image search.
    video_path: a video post instead of a photo; its frames are searched and its speech joins the caption."""
    budget = meta.Budget()
    try:
        yield from _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget, video_path)
    except replay.NotInReplay as e:
        yield {"type": "error", "text": "This check was not recorded, and the demo runs without keys (replay mode). "
                                        "Pick one of the examples, or run Backstory locally with keys. (%s)" % e}
    except search.SearchUnavailable as e:
        yield {"type": "error", "text": str(e)}
    except video.VideoError as e:
        yield {"type": "error", "text": "Could not read the video: %s" % e}
    except meta.BudgetExceeded as e:
        yield {"type": "error", "text": "Stopped: %s." % e}
    except Exception as e:  # noqa: BLE001 - reported to the page, never swallowed silently
        yield {"type": "error", "text": "%s: %s" % (type(e).__name__, e)}


def _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget, video_path=None):
    search_images = [image_bytes]
    if video_path:
        # 0. A video: still frames to search for, and the words spoken in it.
        yield step("frames", "running", "Taking still frames from the video")
        shots = video.frames(video_path)
        if not shots:
            raise video.VideoError("no frames could be read")
        image_bytes, search_images = shots[0]["jpeg"], [f["jpeg"] for f in shots]
        yield step("frames", "done", "%s taken at %s s" % (_count(len(shots), "frame", "frames"),
                                                          ", ".join(str(f["t"]) for f in shots)))
        yield step("speech", "running", "Transcribing what is said in the video")
        wav = video.audio_wav(video_path)
        spoken = video.transcribe(wav, budget=budget) if wav else ""
        yield step("speech", "done", ('Said in the video: "%s"' % spoken[:300]) if spoken else "No speech in the video",
                   transcript=spoken)
        if spoken:
            caption = (caption.strip() + "\n" if caption.strip() else "") + 'Spoken in the video: "%s"' % spoken

    # 1. What does the caption claim?
    yield step("claim", "running", "Reading the caption")
    c = claim.read_claim(caption, posted_on, budget=budget)
    said = " · ".join(str(v) for v in (c.get("event"), c.get("place"), c.get("claimed_date")) if v)
    yield step("claim", "done", "The caption claims: %s" % (said or "nothing checkable"), claim=c)

    # 2. Where else is this photo online?
    # 1b. A post screenshot or collage: find the separate photos in it; each is searched as well.
    if not video_path and matches is None:
        yield step("cutout", "running", "Looking for separate photos inside the post")
        regions = sam.photo_regions(image_bytes, budget=budget)
        search_images = [image_bytes] + [r["jpeg"] for r in regions]
        yield step("cutout", "done", ("Cut out %s; searched along with the whole image" % _count(len(regions), "photo", "separate photos"))
                   if regions else "The image is a single photo", thumbs=[_thumb(r["jpeg"]) for r in regions])

    what = "these frames" if video_path else "this exact photo"
    yield step("search", "running", "Searching the web for %s" % what)
    similar = []
    if matches is not None:
        found_pages = search.from_list(matches)["pages"]
    else:
        results = [search.google_vision(img) for img in search_images]
        found_pages = [p for r in results for p in r["pages"]]
        # Candidates seen for several frames first.
        seen = {}
        for r in results:
            for u in r["similar"]:
                seen[u] = seen.get(u, 0) + 1
        similar = sorted(seen, key=lambda u: -seen[u])
    pages = []
    for p in found_pages:
        fc = search.is_fact_checker(p["url"])
        if fc and exclude_fact_checkers:
            continue
        if p["url"] not in [q["url"] for q in pages]:
            pages.append(dict(p, fact_checker=fc, domain=search.domain(p["url"])))
    # Read news and archive pages first; video, review and social pages rarely say where a photo is from.
    pages.sort(key=lambda p: (p.get("match") == "partial", search.low_value(p["url"])))
    yield step("search", "done", "Found %s on %s" % ("the frames" if video_path else "the photo",
                                                      _count(len(pages), "page", "pages")), count=len(pages))

    # 2b. Few exact matches (typical for video frames and re-encoded copies): check look-alikes one by one.
    if sum(1 for p in pages if p.get("match") == "full") < 2 and similar:
        cands = similar[:config.MAX_SIMILAR]
        yield step("match", "running", "Comparing %s with the post, frame by frame"
                   % _count(len(cands), "look-alike image", "look-alike images"))
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            checks = list(pool.map(lambda u: matcher.same_source(image_bytes, u, budget=budget), cands))
        confirmed = [m for m in checks if m["same"]]
        for m in confirmed:
            if m["url"] not in [q["url"] for q in pages]:
                pages.append({"url": m["url"], "title": "", "image_urls": [m["url"]], "match": "confirmed look-alike",
                              "image_only": True, "fact_checker": search.is_fact_checker(m["url"]),
                              "domain": search.domain(m["url"]), "match_reason": m.get("reason")})
        yield step("match", "done", ("%s the same source: %s" % (
            _count(len(confirmed), "image is", "images are"), "; ".join(search.domain(m["url"]) for m in confirmed)))
            if confirmed else "None of them is the same photo or footage", checked=len(cands))
    if not pages:
        yield from _finish(c, [], None, None, None, budget, "No earlier copy of this photo was found online, "
                                                            "so there is nothing to check the caption against.")
        return

    # 3 + 4. Archive dates and page reading, in parallel.
    read_idx = [i for i, p in enumerate(pages) if not p.get("image_only")][:config.MAX_PAGES]
    to_read = [pages[i] for i in read_idx]
    image_jobs, n = [], 0
    # Image files only known as look-alikes are dated first: their archive date is all there is.
    for i, p in sorted(enumerate(pages), key=lambda ip: not ip[1].get("image_only")):
        for u in p.get("image_urls", [])[:3]:
            if n < config.MAX_ARCHIVE_LOOKUPS:
                image_jobs.append((i, u))
                n += 1
    ev = [{"id": "E%d" % (i + 1), "url": p["url"], "domain": p["domain"], "fact_checker": p["fact_checker"],
           "match": p.get("match"), "image_first": None, "image_snapshot": None, "page_first": None}
          for i, p in enumerate(pages)]
    yield step("archive", "running", "Looking up first archive dates for %s and %s"
               % (_count(len(image_jobs), "image file", "image files"), _count(len(to_read), "page", "pages")))
    if to_read:
        yield step("reader", "running", "Opening %s to see how they describe the photo"
                   % _count(len(to_read), "page", "pages"))
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        futs = {}
        for i in read_idx:
            p = pages[i]
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
    useful = [e for i, e in enumerate(ev) if i in read_idx or e["image_first"]]
    dated = sum(1 for e in useful if e["image_first"] or e["page_first"])
    yield step("archive", "done", "%d of %d page%s dated by the Internet Archive" % (dated, len(useful), "" if len(useful) == 1 else "s"))
    if to_read:
        yield step("reader", "done", _count(sum(1 for e in useful if e.get("relevant")), "page describes", "pages describe") + " the photo")

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
    yield step("judge", "done", "%s. %s" % (WORDS[j["verdict"]], j.get("summary", "")), judged=j)
    yield step("critic", "running", "Checking the judge's reasoning against the evidence")
    cr = verdict.critic(c, useful, j, post_image=image_bytes, budget=budget)
    if not cr["approve"]:
        yield step("critic", "done", "Sent back: %s" % cr.get("problem"), critic=cr, approve=False)
        yield step("judge", "running", "Second attempt after the critic's objection")
        j = verdict.judge(image_bytes, c, useful, critic_note=cr.get("problem"), budget=budget)
        yield step("judge", "done", "%s. %s" % (WORDS[j["verdict"]], j.get("summary", "")), judged=j)
        yield step("critic", "running", "Checking the second attempt")
        cr = verdict.critic(c, useful, j, post_image=image_bytes, budget=budget)
    yield step("critic", "done", "Approved: the cited evidence supports the verdict" if cr["approve"]
               else "Still not convinced: %s" % cr.get("problem"),
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
        said = e.get("described_date")
        if said and ISO.match(str(said)) and (e.get("relevant") or e["id"] in ((judged or {}).get("cited") or [])):
            what = " · ".join(str(v) for v in (e.get("described_event"), e.get("described_place")) if v)
            timeline.append({"date": said, "kind": "described", "id": e["id"],
                             "text": "%s dates the photo here%s" % (e["domain"], (": " + what) if what else ""),
                             "url": e["url"]})
    timeline.sort(key=lambda t: t["date"])
    cited = set((judged or {}).get("cited") or [])
    if rule:
        cited.add(rule["evidence_id"])
    yield {"type": "result", "verdict": final, "basis": basis, "summary": summary, "claim": c,
           "actual": (judged or {}).get("actual"), "rule": rule, "cited": sorted(cited), "evidence": evidence,
           "timeline": timeline, "critic": crit, "cost": budget.summary(), "mode": config.MODE}

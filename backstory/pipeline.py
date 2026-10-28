"""Runs one check and yields progress events, so the web page can show each agent at work.

Event types: "step" (an agent starts or finishes), "evidence" (one row of the evidence table is ready),
"result" (the final answer) and "error".
"""
import base64
import datetime as dt
import concurrent.futures as cf
import io
import re
import tempfile
from pathlib import Path

from PIL import Image

from . import archive, claim, clock, config, matcher, meta, reader, replay, sam, search, verdict, video, witness, xpost

AGENTS = {
    "post": "Post reader · X",
    "frames": "Frame grabber · ffmpeg",
    "speech": "Speech reader · Muse Voice Transcribe",
    "claim": "Claim reader · Muse Spark + web search",
    "cutout": "Photo finder · SAM 3.1",
    "witness": "Scene witness · Muse Spark + Muse Wonder",
    "search": "Image search · Google Vision",
    "clock": "Post clock · code",
    "match": "Match checker · Muse Spark",
    "archive": "Archivist · Internet Archive",
    "reader": "Page reader · Muse Spark",
    "rule": "Date rule · code",
    "judge": "Judge · Muse Spark",
    "critic": "Critic · Muse Wonder",
    "grounds": "Proof check · code",
}


WORDS = {"inconsistent": "Does not fit", "consistent": "Fits", "cannot_tell": "Cannot verify"}
ISO = re.compile(r"^\d{4}(-\d\d){0,2}$")


def step(agent, status, text, **data):
    return {"type": "step", "agent": agent, "label": AGENTS[agent], "status": status, "text": text, **data}


def _guarded(fn, *args, **kw):
    """Run one lookup; a failure (or a lookup missing from a recording) gives None instead of ending the check.
    Running out of budget still stops everything."""
    try:
        return fn(*args, **kw)
    except meta.BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001 - one page or file failing must not lose the others
        return None


def _thumb(jpeg, side=160):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _count(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def _iso(value):
    """'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' as a string if it is a real date, else None."""
    value = str(value or "").strip()
    if not ISO.match(value):
        return None
    parts = [int(x) for x in value.split("-")] + [1, 1]
    try:
        dt.date(parts[0], parts[1], parts[2])
    except ValueError:
        return None
    return value


def _min_date(*dates):
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def run(image_bytes, caption, posted_on=None, matches=None, exclude_fact_checkers=False, video_path=None,
        post_url=None):
    """matches: a fixed search result (evaluation); None means live reverse image search.
    video_path: a video post instead of a photo; its frames are searched and its speech joins the caption.
    post_url: a link to a post on X; its text, date and media replace the other inputs."""
    budget = meta.Budget()
    tmp = []
    try:
        yield from _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget, video_path, post_url,
                        tmp)
    except xpost.PostError as e:
        yield {"type": "error", "text": "Could not read the post: %s" % e}
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
    finally:
        for f in tmp:
            Path(f).unlink(missing_ok=True)


def _run(image_bytes, caption, posted_on, matches, exclude_fact_checkers, budget, video_path=None, post_url=None,
         tmp=None):
    extra = {}
    search_images = [image_bytes]
    search_kinds = ["the photo"]  # what each search image is, for the check graph
    if post_url:
        # 0. A link to a post: take its own text, date and media.
        yield step("post", "running", "Reading the post")
        post = xpost.read(post_url)
        caption, posted_on = post["text"], post["posted_on"] or posted_on
        if post["video"]:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(post["video"])
            video_path = f.name
            tmp.append(f.name)
        elif post["photos"]:
            image_bytes, search_images = post["photos"][0], list(post["photos"])
            search_kinds = ["photo %d" % (i + 1) if len(search_images) > 1 else "the photo"
                            for i in range(len(search_images))]
        elif post["has_media"]:
            raise xpost.PostError("the post's photo or video could not be downloaded")
        else:
            raise xpost.PostError("the post has no photo or video")
        media = "a video" if post["video"] else _count(len(post["photos"]), "photo", "photos")
        yield step("post", "done", '@%s, %s, with %s: "%s"' % (post["author"], post["posted_on"], media, post["text"][:240]),
                   post={k: post[k] for k in ("url", "author", "text", "posted_on")},
                   thumbs=[_thumb(p) for p in post["photos"]])
        extra = {"post": {k: post[k] for k in ("url", "author", "posted_on")},
                 "community_note": post["community_note"]}
    if video_path:
        # 0. A video: still frames to search for, and the words spoken in it.
        yield step("frames", "running", "Taking still frames from the video")
        shots = video.frames(video_path)
        if not shots:
            raise video.VideoError("no frames could be read")
        image_bytes, search_images = shots[0]["jpeg"], [f["jpeg"] for f in shots]
        search_kinds = ["frame at %s s" % f["t"] for f in shots]
        yield step("frames", "done", "%s taken at %s s" % (_count(len(shots), "frame", "frames"),
                                                          ", ".join(str(f["t"]) for f in shots)),
                   thumbs=[_thumb(f["jpeg"]) for f in shots])
        yield step("speech", "running", "Transcribing what is said in the video")
        spoken = video.speech(video_path, budget=budget)
        if spoken is None:
            text = "Transcription failed; the check goes on without the spoken words"
        else:
            text = ('Said in the video: "%s"' % spoken[:300]) if spoken else "No speech in the video"
        yield step("speech", "done", text, transcript=spoken or "")
        if spoken:
            caption = (caption.strip() + "\n" if caption.strip() else "") + 'Spoken in the video: "%s"' % spoken

    # 1. What does the caption claim?
    yield step("claim", "running", "Reading the caption")
    c = claim.read_claim(caption, posted_on, budget=budget)
    said = " · ".join(str(v) for v in (c.get("event"), c.get("place"), c.get("claimed_date")) if v)
    if not c.get("place") and not c.get("period_start"):
        text = "The caption names no place or date to check; the record will still show where the photo comes from"
    else:
        text = "The caption claims: %s" % said
        if c.get("implied"):
            text += " (no date given; presented as news, so taken as no older than %s)" % c["period_start"]
    yield step("claim", "done", text, claim=c)

    # 1b. A post screenshot or collage: find the separate photos in it; each is searched as well.
    if not video_path and matches is None and not post_url:
        yield step("cutout", "running", "Looking for separate photos inside the post")
        regions = sam.photo_regions(image_bytes, budget=budget)
        search_images = [image_bytes] + [r["jpeg"] for r in regions]
        search_kinds = ["the whole image"] + ["cut-out %d" % (i + 1) for i in range(len(regions))]
        yield step("cutout", "done", ("Cut out %s; searched along with the whole image" % _count(len(regions), "photo", "separate photos"))
                   if regions else "The image is a single photo", thumbs=[_thumb(r["jpeg"]) for r in regions])

    # 1c. What does the footage itself show? Readable signs and landmarks, checked frame by frame; for a video,
    # the most distinctive moments are searched as well.
    scene_rows = []
    if config.WITNESS:
        yield step("witness", "running", "Watching the %s for signs, text and landmarks" % ("video" if video_path else "photo"))
        seen = _guarded(witness.look, video_path=video_path, image_bytes=None if video_path else image_bytes,
                        budget=budget)
        if video_path:
            frame_at = lambda t: _guarded(video.frame_at, video_path, t)  # noqa: E731
        else:
            frame_at = lambda t: image_bytes  # noqa: E731
        if seen and video_path:
            taken = [f["t"] for f in shots]
            for t in seen["moments"]:
                if all(abs(t - u) > 1.5 for u in taken):
                    jpeg = frame_at(t)
                    if jpeg:
                        search_images.append(jpeg)
                        search_kinds.append("moment at %s s" % round(t, 1))
                        taken.append(t)
        checked = (_guarded(witness.check, c, seen, frame_at, budget=budget) or []) if seen else []
        for k, x in enumerate([x for x in checked if x["confirmed"]]):
            scene_rows.append({"id": "S%d" % (k + 1), "url": post_url or "", "domain": "the footage itself",
                               "fact_checker": False, "match": "scene", "image_first": None, "image_snapshot": None,
                               "page_first": None, "described_place": x["country"], "quote": x["text"],
                               "scene_t": x["t"], "other_country": x["other_country"], "relevant": True,
                               "check_reason": x["reason"], "image_url": _guarded(_thumb, x["jpeg"], 480)})
        if not seen:
            text = "Could not watch the %s" % ("video" if video_path else "photo")
        else:
            n = len(seen["scene_texts"])
            text = "%s in the scene" % _count(n, "readable text", "readable texts")
            if scene_rows:
                text += "; confirmed by Muse Wonder: " + "; ".join(
                    '"%s" (%s)' % (r["quote"], r["described_place"]) for r in scene_rows)
            elif checked:
                text += "; none confirmed on its frame"
            if video_path and len(search_images) > len(shots):
                text += "; %s added to the search" % _count(len(search_images) - len(shots), "distinctive moment",
                                                          "distinctive moments")
        yield step("witness", "done", text, thumbs=[t for t in (_guarded(_thumb, x["jpeg"]) for x in checked if x["confirmed"]) if t][:2],
                   scene=[{k: r[k] for k in ("id", "quote", "described_place", "scene_t",
                                                                      "other_country")} for r in scene_rows])

    # 2. Where else is this photo online?
    what = "these frames" if video_path else "this exact photo"
    yield step("search", "running", "Searching the web for %s" % what)
    similar = []
    if matches is not None:
        found_pages = search.from_list(matches)["pages"]
    else:
        # The main image must be searchable; extra cut-outs and frames may fail without ending the check.
        results = [(0, search.google_vision(search_images[0]))]
        results += [(i, r) for i, r in ((i, _guarded(search.google_vision, img))
                                        for i, img in enumerate(search_images) if i) if r]
        # found_by: which search image (frame, cut-out) the page was found for, to compare like with like later.
        found_pages = [dict(p, found_by=i) for i, r in results for p in r["pages"]]
        results = [r for _, r in results]
        # Candidates seen for several frames first.
        seen = {}
        for r in results:
            for u in r["similar"]:
                seen[u] = seen.get(u, 0) + 1
        similar = sorted(seen, key=lambda u: -seen[u])
        if exclude_fact_checkers:
            similar = [u for u in similar if not search.looks_like_debunk(u)]
    pages, by_url = [], {}
    for p in found_pages:
        fc = search.is_fact_checker(p["url"])
        if exclude_fact_checkers and search.looks_like_debunk(p["url"]):
            continue
        if exclude_fact_checkers:
            p = dict(p, image_urls=[u for u in p.get("image_urls", []) if not search.looks_like_debunk(u)])
        q = by_url.get(p["url"])
        if q is None:
            q = by_url[p["url"]] = dict(p, image_urls=list(p.get("image_urls", [])), fact_checker=fc,
                                        domain=search.domain(p["url"]))
            pages.append(q)
        else:
            # The same page found for another search image (a cut-out, another frame): keep the best match.
            new = [u for u in p.get("image_urls", []) if u not in q["image_urls"]]
            if p.get("match") == "full" and q.get("match") != "full":
                q["match"], q["image_urls"] = "full", new + q["image_urls"]
            else:
                q["image_urls"] += new
    # Read news and archive pages first; video, review and social pages rarely say where a photo is from.
    pages.sort(key=lambda p: (p.get("match") == "partial", search.low_value(p["url"])))
    yield step("search", "done", "Found %s on %s" % ("the frames" if video_path else "the photo",
                                                      _count(len(pages), "page", "pages")), count=len(pages),
               inputs=[{"kind": k, "thumb": _guarded(_thumb, img, 120)} for k, img in zip(search_kinds, search_images)])

    # 2a. Copies on X, TikTok and YouTube: their exact posting dates, from the post id or the page metadata.
    own = clock.X_STATUS.match(post_url or "")
    if own:  # the post being checked is not evidence about itself
        pages = [p for p in pages if not (clock.X_STATUS.match(p["url"]) or [None, None])[1] == own.group(1)]
    posts = [p for p in pages if clock.is_post(p["url"])][:config.MAX_CLOCK]
    if posts:
        yield step("clock", "running", "Reading the posting dates of %s" % _count(len(posts), "copy on X, TikTok or YouTube",
                                                                                 "copies on X, TikTok or YouTube"))
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            for p, t in zip(posts, pool.map(lambda p: _guarded(clock.posted, p["url"]), posts)):
                if t:
                    p["posted"], p["posted_how"] = t["date"], t["how"]
            # A copy posted before the claimed date can decide the verdict: get its picture for the match checker.
            early = [p for p in posts if p.get("posted") and c.get("period_start") and p["posted"] < c["period_start"]
                     and not p.get("image_urls")]
            # Kept apart from image_urls: a cover image is for comparing only. It is not the file that matched,
            # so its archive date must never date the page.
            for p, u in zip(early, pool.map(lambda p: _guarded(clock.thumbnail, p["url"]), early)):
                if u:
                    p["thumb"] = u
        dated = sorted(p["posted"] for p in posts if p.get("posted"))
        yield step("clock", "done", ("%d of %d dated; earliest %s" % (len(dated), len(posts), dated[0])) if dated
                   else "No posting date found", dated=len(dated))

    # 2b. Few exact matches (typical for video frames and re-encoded copies): check look-alikes one by one.
    if sum(1 for p in pages if p.get("match") == "full") < 2 and similar:
        cands = similar[:config.MAX_SIMILAR]
        yield step("match", "running", "Comparing %s with the post, frame by frame"
                   % _count(len(cands), "look-alike image", "look-alike images"))
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            checks = list(pool.map(lambda u: _guarded(matcher.same_source, image_bytes, u, budget=budget)
                                   or {"url": u, "same": False}, cands))
        confirmed = [m for m in checks if m["same"]]
        for m in confirmed:
            if m["url"] not in [q["url"] for q in pages]:
                pages.append({"url": m["url"], "title": "", "image_urls": [m["url"]], "match": "confirmed look-alike",
                              "image_only": True, "fact_checker": search.is_fact_checker(m["url"]),
                              "domain": search.domain(m["url"]), "match_reason": m.get("reason")})
        yield step("match", "done", ("%s the same source: %s" % (
            _count(len(confirmed), "image is", "images are"), "; ".join(search.domain(m["url"]) for m in confirmed)))
            if confirmed else "None of them is the same photo or footage", checked=len(cands))
    # 2c. Partial matches (crops, re-encoded video frames): the match checker compares each page's image with the
    # frame or photo it was found for. Confirmed ones count as the same source; the rest stay "partial".
    partial = [p for p in pages if p.get("match") == "partial" and (p.get("image_urls") or p.get("thumb"))
               and not p.get("image_only")]
    # Copies posted before the claimed date are checked first: they are the ones that can decide the verdict.
    start = c.get("period_start")
    # They get their own places, so they never push out the partial matches on news pages.
    decisive = [p for p in partial if start and p.get("posted") and p["posted"] < start][:config.MAX_EARLY]
    rest = [p for p in partial if p not in decisive]
    if matches is not None:
        partial = []
    elif sum(1 for p in pages if p.get("match") == "full") >= 2:
        partial = decisive
    else:
        partial = rest[:config.MAX_PARTIAL] + decisive
    if partial:
        yield step("match", "running", "Comparing %s with the post"
                   % _count(len(partial), "partly matching image", "partly matching images"))
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            checks = list(pool.map(lambda p: _guarded(matcher.same_source, search_images[p.get("found_by", 0)],
                                                      (p.get("image_urls") or [p.get("thumb")])[0], budget=budget)
                                     or {"same": False}, partial))
        for p, m in zip(partial, checks):
            if m["same"]:
                p["match"], p["match_reason"] = "confirmed look-alike", m.get("reason")
        ok = [p for p, m in zip(partial, checks) if m["same"]]
        yield step("match", "done", ("%s the same source: %s" % (
            _count(len(ok), "partial match is", "partial matches are"), "; ".join(p["domain"] for p in ok)))
            if ok else "None of the partial matches is the same photo or footage", checked=len(partial))
        pages.sort(key=lambda p: (p.get("match") == "partial", search.low_value(p["url"])))
    if not pages and not scene_rows:
        yield from _finish(c, [], None, None, None, budget, extra, "No earlier copy of this photo was found online, "
                                                            "so there is nothing to check the caption against.")
        return

    # 3 + 4. Archive dates and page reading, in parallel.
    read_idx = [i for i, p in enumerate(pages) if not p.get("image_only")][:config.MAX_PAGES]
    to_read = [pages[i] for i in read_idx]
    image_jobs, queued = [], set()
    # Image files only known as look-alikes are dated first: their archive date is all there is.
    for i, p in sorted(enumerate(pages), key=lambda ip: not ip[1].get("image_only")):
        for u in p.get("image_urls", [])[:3]:
            if len(image_jobs) < config.MAX_ARCHIVE_LOOKUPS and u not in queued:
                image_jobs.append((i, u))
                queued.add(u)
    ev = [{"id": "E%d" % (i + 1), "url": p["url"], "domain": p["domain"], "fact_checker": p["fact_checker"],
           "match": p.get("match"), "image_first": None, "image_snapshot": None, "page_first": None,
           "page_published": p.get("posted"), "date_source": p.get("posted_how"),
           "image_url": (p.get("image_urls") or [p.get("thumb")])[0], "found_by": p.get("found_by")}
          for i, p in enumerate(pages)]
    yield step("archive", "running", "Looking up first archive dates for %s and %s"
               % (_count(len(image_jobs), "image file", "image files"), _count(len(to_read), "page", "pages")))
    if to_read:
        yield step("reader", "running", "Opening %s to see how they describe the photo"
                   % _count(len(to_read), "page", "pages"))
    pool = cf.ThreadPoolExecutor(max_workers=5)
    try:
        futs = {}
        for i in read_idx:
            p = pages[i]
            futs[pool.submit(_guarded, reader.read_page, p["url"], p.get("image_urls", []), budget)] = ("read", i, None)
            futs[pool.submit(_guarded, archive.first_capture, p["url"])] = ("page", i, None)
        for i, u in image_jobs:
            futs[pool.submit(_guarded, archive.first_capture, u)] = ("image", i, u)
        for f in cf.as_completed(futs):
            kind, i, _ = futs[f]
            res = f.result()
            e = ev[i]
            if res is None:  # this one lookup failed; the others still count
                if kind == "read":
                    e.update(opened=False)
                continue
            if kind == "read":
                e.update(opened=res.get("opened"), title=res.get("title"),
                         page_published=e.get("page_published") if e.get("date_source") else res.get("page_date"),
                         described_place=res.get("place"), described_date=res.get("date"),
                         described_event=res.get("event"), quote=res.get("quote"), relevant=res.get("relevant"))
            elif kind == "page":
                e["page_first"] = res["date"]
                e["page_snapshot"] = res["snapshot"]
            elif res["date"] and (not e["image_first"] or res["date"] < e["image_first"]):
                e["image_first"], e["image_snapshot"] = res["date"], res["snapshot"]
            yield {"type": "evidence", "row": e}
    except meta.BudgetExceeded:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    # A dated copy on X, TikTok or YouTube joins the table only when it is the same footage; unconfirmed partial
    # matches with dates only distract the judge.
    useful = [e for i, e in enumerate(ev) if i in read_idx or e["image_first"]
              or (e.get("date_source") and e["match"] in ("full", "confirmed look-alike"))] + scene_rows
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
    elif not c.get("period_start"):
        yield step("rule", "done", "Not applicable: the caption gives no date", fired=False)
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
    g = None
    if not rule and cr["approve"] and j["verdict"] == "inconsistent":
        # 7. The code checks that the approved "does not fit" rests on proof it can verify in the table.
        g = verdict.grounds(c, useful, j)
        yield step("grounds", "done", ("Proof verified: %s" % g["text"]) if g["ok"]
                   else "Not enough proof: %s" % g["text"], grounds=g)
    yield from _finish(c, useful, rule, j, cr, budget, extra, grounds=g)


def _finish(c, evidence, rule, judged, crit, budget, extra, empty_reason=None, grounds=None):
    if rule:
        final, basis = "inconsistent", "date rule"
        summary = (judged or {}).get("summary") if (judged or {}).get("verdict") == "inconsistent" else None
        summary = summary or ("An archived copy of this image file is dated %s, %d days before the earliest date "
                              "the caption allows." % (rule["image_first"], rule["days_before"]))
    elif grounds and not grounds["ok"]:
        final, basis = "cannot_tell", "proof too weak"
        summary = ("There are signs against the caption, but not enough proof: %s. %s"
                   % (grounds["text"], judged.get("summary") or "")).strip()
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
        said = _iso(e.get("described_date"))
        if said and (e.get("relevant") or e["id"] in ((judged or {}).get("cited") or [])):
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
           "timeline": timeline, "critic": crit, "grounds": grounds, "cost": budget.summary(), "mode": config.MODE, **extra}

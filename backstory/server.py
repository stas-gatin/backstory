"""Web app: upload a photo with its caption (or pick an example) and watch the agents work.

Run: uvicorn backstory.server:app --port 8000
"""
import json
import os
import time
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import config, limits, media, pipeline

WEB = config.ROOT / "web"
EXAMPLES = Path(os.environ.get("BACKSTORY_EXAMPLES_DIR", config.ROOT / "examples"))
MAX_UPLOAD = 20 * 1024 * 1024
MAX_VIDEO = 60 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

app = FastAPI(title="Backstory")


def _examples():
    f = EXAMPLES / "examples.json"
    return json.loads(f.read_text()) if f.exists() else []


def _visitor(request):
    # Behind a proxy (Render, Docker), the visitor is the first address in X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


@app.get("/api/status")
def status(request: Request):
    live = limits.status(_visitor(request)) if config.MODE == "live" else {"live": False, "reason": "no keys"}
    return {"mode": config.MODE, "meta_key": bool(config.MODEL_API_KEY),
            "image_search_key": bool(config.GOOGLE_VISION_API_KEY), "live": live}


def _live(request, events):
    """A new check (not a recorded example): limited on a public copy, and counted when it ends."""
    if config.MODE != "live":
        return events
    try:
        limits.start(_visitor(request))
    except limits.Refused as e:
        raise HTTPException(429, str(e))
    return limits.watch(events)


@app.get("/api/examples")
def examples():
    return [{k: e[k] for k in ("id", "title", "blurb", "caption", "posted_on", "credit", "kind", "post_url", "preview", "image_url", "fresh") if k in e} for e in _examples()]


@app.get("/api/examples/{ex_id}/image")
def example_image(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id and e.get("image"):
            return FileResponse(EXAMPLES / e["image"])
        if e["id"] == ex_id and str(e.get("image_url") or "").startswith("https://pbs.twimg.com/"):
            return RedirectResponse(e["image_url"])  # the post's own image, served by X
    raise HTTPException(404)


# A recorded run replays in a blink; a short pause per step lets a viewer follow the agents. The result says
# "recorded run". The pause is off for live checks, where the agents' own time is shown; an example is always
# paced, in live mode too.
PACE = float(os.environ.get("BACKSTORY_PACE", "1" if config.MODE == "replay" else "0"))
RECORDED_PACE = float(os.environ.get("BACKSTORY_RECORDED_PACE", "1"))


def _ndjson(events, pace):
    for ev in events:
        yield json.dumps(ev, ensure_ascii=False) + "\n"
        if pace and ev.get("type") == "step":
            time.sleep(pace * (0.25 if ev["status"] == "running" else 0.55))
        elif pace and ev.get("type") == "evidence":
            time.sleep(pace * 0.06)


def _stream(events, cleanup=None, pace=None):
    # The temporary video is removed after the response, even if the client leaves early.
    task = BackgroundTask(lambda: Path(cleanup).unlink(missing_ok=True)) if cleanup else None
    return StreamingResponse(_ndjson(events, PACE if pace is None else pace), media_type="application/x-ndjson", background=task)


@app.post("/api/check")
async def check(request: Request, caption: str = Form(""), posted_on: str = Form(""), example_id: str = Form(""),
                post_url: str = Form(""), image: UploadFile | None = File(None)):
    video_path, cleanup = None, None
    if post_url.strip():
        return _stream(_live(request, pipeline.run(None, "", None, post_url=post_url.strip())))
    if example_id:
        ex = next((e for e in _examples() if e["id"] == example_id), None)
        if not ex:
            raise HTTPException(404, "unknown example")
        if ex.get("recording"):
            # A recorded check of a post on X: its events as they were, without the post's media.
            lines = (EXAMPLES / ex["recording"]).read_text().splitlines()
            return _stream((json.loads(l) for l in lines if l.strip()), pace=RECORDED_PACE)
        caption, posted_on = ex["caption"], ex.get("posted_on") or ""
        # Dataset cases carry their recorded search results instead of a live image search.
        matches = ex.get("matches")
        if ex.get("kind") == "link":
            return _stream(pipeline.run(None, "", None, post_url=ex["post_url"]), pace=RECORDED_PACE)
        if ex.get("kind") == "video":
            data, video_path = None, str(EXAMPLES / ex["video"])
        else:
            data = (EXAMPLES / ex["image"]).read_bytes()
    else:
        if image is None or not caption.strip():
            raise HTTPException(400, "send a photo or video and its caption")
        is_video = ((image.content_type or "").startswith("video/")
                    or Path(image.filename or "").suffix.lower() in VIDEO_SUFFIXES)
        limit = MAX_VIDEO if is_video else MAX_UPLOAD
        if image.size is not None and image.size > limit:  # checked before reading the body into memory
            raise HTTPException(413, "file larger than %d MB" % (limit // 2**20))
        data, matches = await image.read(limit + 1), None
        if len(data) > limit:
            raise HTTPException(413, "file larger than %d MB" % (limit // 2**20))
        if is_video:
            with tempfile.NamedTemporaryFile(suffix=Path(image.filename or "v.mp4").suffix, delete=False) as f:
                f.write(data)
            data, video_path = None, f.name
            cleanup = f.name
        else:
            try:
                data = media.normalise_image(data)
            except media.BadMedia as e:
                raise HTTPException(400, str(e))
    events = pipeline.run(data, caption, posted_on or None, matches=matches, video_path=video_path)
    if not example_id:
        events = _live(request, events)
    # An example replays its recorded answers: paced, so its agents can be watched.
    return _stream(events, cleanup, pace=RECORDED_PACE if example_id else None)


@app.get("/api/examples/{ex_id}/video")
def example_video(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id and e.get("kind") == "video":
            return FileResponse(EXAMPLES / e["video"])
    raise HTTPException(404)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/check")
def check_page():
    return FileResponse(WEB / "index.html")


@app.get("/tested")
def tested():
    return FileResponse(WEB / "tested.html")


@app.get("/record")
def record():
    return FileResponse(WEB / "record.html")


@app.get("/api/record")
def record_data():
    """Every post checked in Tests H2–H6, with its verdict and evidence (eval/track_record.py)."""
    f = config.ROOT / "eval" / "track_record.json"
    return FileResponse(f) if f.exists() else []


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.middleware("http")
async def _revalidate(request, call_next):
    # The page's own files change between versions: the browser asks again each time instead of keeping a stale copy.
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path in ("/", "/check", "/tested", "/record"):
        response.headers["Cache-Control"] = "no-cache"
    return response

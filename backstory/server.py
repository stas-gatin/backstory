"""Web app: upload a photo with its caption (or pick an example) and watch the agents work.

Run: uvicorn backstory.server:app --port 8000
"""
import json
import os
import time
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import config, media, pipeline

WEB = config.ROOT / "web"
EXAMPLES = Path(os.environ.get("BACKSTORY_EXAMPLES_DIR", config.ROOT / "examples"))
MAX_UPLOAD = 20 * 1024 * 1024
MAX_VIDEO = 60 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

app = FastAPI(title="Backstory")


def _examples():
    f = EXAMPLES / "examples.json"
    return json.loads(f.read_text()) if f.exists() else []


@app.get("/api/status")
def status():
    return {"mode": config.MODE, "meta_key": bool(config.MODEL_API_KEY),
            "image_search_key": bool(config.GOOGLE_VISION_API_KEY)}


@app.get("/api/examples")
def examples():
    return [{k: e[k] for k in ("id", "title", "blurb", "caption", "posted_on", "credit", "kind", "post_url") if k in e} for e in _examples()]


@app.get("/api/examples/{ex_id}/image")
def example_image(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id and e.get("image"):
            return FileResponse(EXAMPLES / e["image"])
    raise HTTPException(404)


# A recorded run replays in a blink; a short pause per step lets a viewer follow the agents. The result says
# "recorded run", and the pause is off in live mode, where the agents' own time is shown.
PACE = float(os.environ.get("BACKSTORY_PACE", "1" if config.MODE == "replay" else "0"))


def _ndjson(events):
    for ev in events:
        yield json.dumps(ev, ensure_ascii=False) + "\n"
        if PACE and ev.get("type") == "step":
            time.sleep(PACE * (0.25 if ev["status"] == "running" else 0.55))
        elif PACE and ev.get("type") == "evidence":
            time.sleep(PACE * 0.06)


def _stream(events, cleanup=None):
    # The temporary video is removed after the response, even if the client leaves early.
    task = BackgroundTask(lambda: Path(cleanup).unlink(missing_ok=True)) if cleanup else None
    return StreamingResponse(_ndjson(events), media_type="application/x-ndjson", background=task)


@app.post("/api/check")
async def check(caption: str = Form(""), posted_on: str = Form(""), example_id: str = Form(""),
                post_url: str = Form(""), image: UploadFile | None = File(None)):
    video_path, cleanup = None, None
    if post_url.strip():
        return _stream(pipeline.run(None, "", None, post_url=post_url.strip()))
    if example_id:
        ex = next((e for e in _examples() if e["id"] == example_id), None)
        if not ex:
            raise HTTPException(404, "unknown example")
        caption, posted_on = ex["caption"], ex.get("posted_on") or ""
        # Dataset cases carry their recorded search results instead of a live image search.
        matches = ex.get("matches")
        if ex.get("kind") == "link":
            return _stream(pipeline.run(None, "", None, post_url=ex["post_url"]))
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
    return _stream(events, cleanup)


@app.get("/api/examples/{ex_id}/video")
def example_video(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id and e.get("kind") == "video":
            return FileResponse(EXAMPLES / e["video"])
    raise HTTPException(404)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/tested")
def tested():
    return FileResponse(WEB / "tested.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")

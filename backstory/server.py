"""Web app: upload a photo with its caption (or pick an example) and watch the agents work.

Run: uvicorn backstory.server:app --port 8000
"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, pipeline

WEB = config.ROOT / "web"
EXAMPLES = Path(os.environ.get("BACKSTORY_EXAMPLES_DIR", config.ROOT / "examples"))
MAX_UPLOAD = 8 * 1024 * 1024
MAX_VIDEO = 60 * 1024 * 1024

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
    return [{k: e[k] for k in ("id", "title", "caption", "posted_on", "credit", "kind", "post_url") if k in e} for e in _examples()]


@app.get("/api/examples/{ex_id}/image")
def example_image(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id:
            return FileResponse(EXAMPLES / e["image"])
    raise HTTPException(404)


def _ndjson(events, cleanup=None):
    try:
        for ev in events:
            yield json.dumps(ev, ensure_ascii=False) + "\n"
    finally:
        if cleanup:
            Path(cleanup).unlink(missing_ok=True)


@app.post("/api/check")
async def check(caption: str = Form(""), posted_on: str = Form(""), example_id: str = Form(""),
                post_url: str = Form(""), image: UploadFile | None = File(None)):
    video_path, cleanup = None, None
    if post_url.strip():
        return StreamingResponse(_ndjson(pipeline.run(None, "", None, post_url=post_url.strip())),
                                 media_type="application/x-ndjson")
    if example_id:
        ex = next((e for e in _examples() if e["id"] == example_id), None)
        if not ex:
            raise HTTPException(404, "unknown example")
        caption, posted_on = ex["caption"], ex.get("posted_on") or ""
        # Dataset cases carry their recorded search results instead of a live image search.
        matches = ex.get("matches")
        if ex.get("kind") == "link":
            return StreamingResponse(_ndjson(pipeline.run(None, "", None, post_url=ex["post_url"])),
                                     media_type="application/x-ndjson")
        if ex.get("kind") == "video":
            data, video_path = None, str(EXAMPLES / ex["video"])
        else:
            data = (EXAMPLES / ex["image"]).read_bytes()
    else:
        if image is None or not caption.strip():
            raise HTTPException(400, "send a photo or video and its caption")
        data, matches = await image.read(), None
        if (image.content_type or "").startswith("video/"):
            if len(data) > MAX_VIDEO:
                raise HTTPException(413, "video larger than 60 MB")
            with tempfile.NamedTemporaryFile(suffix=Path(image.filename or "v.mp4").suffix, delete=False) as f:
                f.write(data)
            data, video_path = None, f.name
            cleanup = f.name
        elif len(data) > MAX_UPLOAD:
            raise HTTPException(413, "photo larger than 8 MB")
    events = pipeline.run(data, caption, posted_on or None, matches=matches, video_path=video_path)
    return StreamingResponse(_ndjson(events, cleanup), media_type="application/x-ndjson")


@app.get("/api/examples/{ex_id}/video")
def example_video(ex_id: str):
    for e in _examples():
        if e["id"] == ex_id and e.get("kind") == "video":
            return FileResponse(EXAMPLES / e["video"])
    raise HTTPException(404)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")

"""Server behaviour on bad input: rejected before any model is called."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backstory import pipeline, server


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fake_run(*a, **k):
        calls.append((a, k))
        yield {"type": "result", "verdict": "cannot_tell"}
    monkeypatch.setattr(pipeline, "run", fake_run)
    c = TestClient(server.app)
    c.calls = calls
    return c


def png(w=200, h=150):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "navy").save(buf, format="PNG")
    return buf.getvalue()


def test_non_image_is_rejected_without_a_check(client):
    r = client.post("/api/check", data={"caption": "Valencia yesterday"},
                    files={"image": ("a.pdf", b"%PDF-1.4 hello", "application/pdf")})
    assert r.status_code == 400 and "not a photo" in r.json()["detail"]
    assert client.calls == []


def test_missing_caption_is_rejected(client):
    r = client.post("/api/check", data={"caption": "  "}, files={"image": ("a.png", png(), "image/png")})
    assert r.status_code == 400 and client.calls == []


def test_tiny_image_is_rejected(client):
    r = client.post("/api/check", data={"caption": "x"}, files={"image": ("a.png", png(10, 10), "image/png")})
    assert r.status_code == 400 and client.calls == []


def test_photo_is_normalised_to_jpeg_and_streamed(client):
    r = client.post("/api/check", data={"caption": "Valencia yesterday", "posted_on": "2024-10-30"},
                    files={"image": ("a.png", png(), "image/png")})
    assert r.status_code == 200
    assert json.loads(r.text.strip().splitlines()[-1])["type"] == "result"
    (data, caption, posted), _ = client.calls[0]
    assert data[:2] == b"\xff\xd8" and caption == "Valencia yesterday" and posted == "2024-10-30"


def test_post_link_goes_to_the_pipeline(client):
    r = client.post("/api/check", data={"post_url": "https://x.com/a/status/42"})
    assert r.status_code == 200
    assert client.calls[0][1]["post_url"] == "https://x.com/a/status/42"


def test_status_reports_mode(client):
    assert client.get("/api/status").json()["mode"] in ("live", "replay")


def test_video_recognised_by_extension(client, monkeypatch):
    r = client.post("/api/check", data={"caption": "Florida now"},
                    files={"image": ("clip.mov", b"\x00\x00\x00\x18ftypqt  ", "application/octet-stream")})
    assert r.status_code == 200
    assert client.calls[0][1]["video_path"].endswith(".mov")


def test_oversized_photo_rejected(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_UPLOAD", 1000)
    r = client.post("/api/check", data={"caption": "x"}, files={"image": ("a.png", png(400, 400), "image/png")})
    assert r.status_code == 413 and client.calls == []

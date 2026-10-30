"""Server behaviour on bad input: rejected before any model is called."""
import io
import json
import time

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
    monkeypatch.setattr(server.config, "MODE", "replay")  # no live-check limits in these tests
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


# Live checks on a public copy -----------------------------------------------------------------------------------------

@pytest.fixture
def live(monkeypatch, tmp_path):
    from backstory import limits
    monkeypatch.setattr(server.config, "MODE", "live")
    monkeypatch.setattr(limits, "STATE", tmp_path / "limits.json")
    monkeypatch.setattr(limits, "PER_VISITOR", 2)
    monkeypatch.setattr(limits, "_running", [0])
    answers = []

    def fake_run(*a, **k):
        yield answers.pop(0) if answers else {"type": "result", "verdict": "cannot_tell", "cost": {"usd": 0.1}}
    monkeypatch.setattr(pipeline, "run", fake_run)
    c = TestClient(server.app)
    c.answers, c.limits = answers, limits
    return c


def post(c, ip="1.2.3.4"):
    return c.post("/api/check", data={"post_url": "https://x.com/a/status/42"}, headers={"x-forwarded-for": ip})


def test_each_visitor_gets_a_few_live_checks_a_day(live):
    assert post(live).status_code == 200 and post(live).status_code == 200
    r = post(live)
    assert r.status_code == 429 and "live checks for today" in r.json()["detail"]
    assert post(live, ip="5.6.7.8").status_code == 200  # another visitor still can


def test_live_checks_pause_when_the_meta_api_stops_answering(live):
    live.answers.append({"type": "error", "text": "RuntimeError: Meta API call failed: HTTP 402: insufficient credit",
                         "cost": {"usd": 0}})
    post(live)
    r = post(live, ip="9.9.9.9")
    assert r.status_code == 429 and "paused" in r.json()["detail"]
    assert live.get("/api/status").json()["live"]["live"] is False


def test_daily_budget_stops_live_checks(live, monkeypatch):
    monkeypatch.setattr(live.limits, "DAY_USD", 0.15)
    post(live), post(live, ip="2.2.2.2")
    assert post(live, ip="3.3.3.3").status_code == 429


def test_recorded_examples_are_never_limited(live, monkeypatch, tmp_path):
    (tmp_path / "examples.json").write_text(json.dumps([{"id": "r", "kind": "recorded", "recording": "r.ndjson",
                                                         "caption": "c"}]))
    (tmp_path / "r.ndjson").write_text(json.dumps({"type": "result", "verdict": "inconsistent"}) + "\n")
    monkeypatch.setattr(server, "EXAMPLES", tmp_path)
    for _ in range(5):
        r = live.post("/api/check", data={"example_id": "r"}, headers={"x-forwarded-for": "1.1.1.1"})
        assert r.status_code == 200


def test_an_example_paced_by_the_page_comes_without_pauses(live, monkeypatch, tmp_path):
    steps = [{"type": "step", "agent": "post", "status": s} for s in ("running", "done")] * 5
    (tmp_path / "examples.json").write_text(json.dumps([{"id": "r", "kind": "recorded", "recording": "r.ndjson",
                                                         "caption": "c"}]))
    (tmp_path / "r.ndjson").write_text("".join(json.dumps(e) + "\n" for e in steps + [{"type": "result"}]))
    monkeypatch.setattr(server, "EXAMPLES", tmp_path)
    monkeypatch.setattr(server, "RECORDED_PACE", 1.0)
    t = time.monotonic()
    r = live.post("/api/check", data={"example_id": "r", "paced_here": "1"})
    assert r.status_code == 200 and len(r.text.splitlines()) == 11 and time.monotonic() - t < 1


def test_every_committed_example_replays_a_recording():
    # A click on an example must never start a live check: it would cost money and take minutes.
    examples = json.loads((server.config.ROOT / "examples" / "examples.json").read_text())
    assert examples and all((server.config.ROOT / "examples" / e["recording"]).exists() for e in examples if e.get("recording"))
    assert [e["id"] for e in examples if not e.get("recording")] == []

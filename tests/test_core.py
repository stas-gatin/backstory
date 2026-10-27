"""Tests for the parts that do not need the network. External calls are replaced by stand-ins."""
import io
import json

import pytest
from PIL import Image

from backstory import config, meta, pipeline, replay, sam, search, verdict, xpost


def jpeg(w=64, h=48, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def replay_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPLAY_DIR", tmp_path)
    return tmp_path


# Date rule ---------------------------------------------------------------------------------------------------------

def ev(i, **kw):
    return {"id": "E%d" % i, "domain": "example.org", "url": "https://example.org/%d" % i, "match": "full", **kw}


def test_date_rule_fires_on_exact_match_archived_before_claim():
    r = verdict.date_rule({"period_start": "2025-01-07"}, [ev(1, image_first="2023-08-24"), ev(2)])
    assert r["evidence_id"] == "E1" and r["days_before"] == 502


def test_date_rule_needs_more_than_one_day():
    assert verdict.date_rule({"period_start": "2025-01-07"}, [ev(1, image_first="2025-01-06")]) is None


def test_date_rule_picks_earliest_copy():
    r = verdict.date_rule({"period_start": "2025-01-07"},
                          [ev(1, image_first="2024-01-01"), ev(2, image_first="2020-05-05")])
    assert r["evidence_id"] == "E2"


def test_date_rule_ignores_look_alikes_and_missing_start():
    look = [ev(1, image_first="2020-01-01", match="confirmed look-alike")]
    assert verdict.date_rule({"period_start": "2025-01-07"}, look) is None
    assert verdict.date_rule({"period_start": None}, [ev(1, image_first="2020-01-01")]) is None


# Search helpers ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.cbsnews.com/news/x", "cbsnews.com"),
    ("https://i0.wp.com/yaleclimateconnections.org/wp-content/a.jpg?w=1", "yaleclimateconnections.org"),
    ("https://i0.wp.com/", "i0.wp.com"),
    ("https://m.yelp.com/biz/a", "m.yelp.com"),
])
def test_domain(url, expected):
    assert search.domain(url) == expected


def test_fact_checkers_and_low_value_pages():
    assert search.is_fact_checker("https://maldita.es/malditobulo/x")
    assert search.is_fact_checker("https://www.snopes.com/fact-check/x")
    assert not search.is_fact_checker("https://www.cbsnews.com/x")
    assert search.low_value("https://www.youtube.com/watch?v=1")
    assert search.low_value("https://m.yelp.com/biz/a")
    assert not search.low_value("https://www.box.com/x")


# X posts -----------------------------------------------------------------------------------------------------------

def test_post_id_from_links():
    assert xpost.post_id("https://x.com/denverbitcoin/status/1839114088284066111?s=20") == "1839114088284066111"
    assert xpost.post_id("https://twitter.com/a/status/42") == "42"
    with pytest.raises(xpost.PostError):
        xpost.post_id("https://example.com/status/42")


def test_post_token_matches_known_value():
    # This value was accepted by X's embed endpoint on 2026-10-27.
    assert xpost._token("1839114088284066111") == "4ghqwifxglf2i5n"


def test_read_post_from_replay(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "replay")
    data = {"__typename": "Tweet", "created_at": "2024-09-26T01:25:42.000Z", "display_text_range": [0, 40],
            "text": "This is from hurricane Helene right now https://t.co/abc", "user": {"screen_name": "someone"},
            "mediaDetails": [], "birdwatch_pivot": {"subtitle": {"text": "From 2022."}}}
    replay.store("xpost", {"id": "42"}, data)
    p = xpost.read("https://x.com/someone/status/42")
    assert p["text"] == "This is from hurricane Helene right now"
    assert p["posted_on"] == "2024-09-26" and p["community_note"] == "From 2022."


def test_deleted_post(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "replay")
    replay.store("xpost", {"id": "7"}, {"missing": True})
    with pytest.raises(xpost.PostError):
        xpost.read("https://x.com/a/status/7")


# Replay ------------------------------------------------------------------------------------------------------------

def test_replay_mode_never_calls_out(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "replay")
    with pytest.raises(replay.NotInReplay):
        replay.cached("meta", {"q": 1}, lambda: pytest.fail("network call in replay mode"))


def test_live_mode_records_then_reuses(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "live")
    calls = []
    assert replay.cached("meta", {"q": 1}, lambda: calls.append(1) or {"a": 1}) == {"a": 1}
    assert replay.cached("meta", {"q": 1}, lambda: calls.append(1) or {"a": 2}) == {"a": 1}
    assert len(calls) == 1


def test_failed_answers_are_not_recorded(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "live")
    replay.cached("wayback", {"u": 1}, lambda: {"ok": False}, keep=lambda r: r["ok"])
    assert replay.lookup("wayback", {"u": 1}) is None


# SAM photo regions -------------------------------------------------------------------------------------------------

def test_photo_regions_drops_nested_and_tiny_boxes(monkeypatch):
    img = jpeg(1000, 1000)
    monkeypatch.setattr(sam, "boxes", lambda b, budget=None: [
        (0, 0, 500, 1000, 0.8),       # left photo of a collage
        (500, 0, 1000, 1000, 0.7),    # right photo
        (100, 100, 300, 300, 0.9),    # picture inside the left photo: nested, dropped
        (900, 900, 950, 950, 0.9),    # tiny, dropped
        (0, 0, 1000, 1000, 0.3),      # low confidence, dropped
    ])
    regions = sam.photo_regions(img)
    assert [r["box"] for r in regions] == [(0, 0, 500, 1000), (500, 0, 1000, 1000)]


def test_photo_regions_single_photo_returns_nothing(monkeypatch):
    monkeypatch.setattr(sam, "boxes", lambda b, budget=None: [(0, 0, 990, 995, 0.9)])
    assert sam.photo_regions(jpeg(1000, 1000)) == []


# Budget ------------------------------------------------------------------------------------------------------------

def test_budget_stops_at_cap():
    b = meta.Budget(cap=0.01)
    b.add(config.SPARK, {"input_tokens": 10_000, "output_tokens": 0})
    with pytest.raises(meta.BudgetExceeded):
        b.check()


# Whole pipeline with stand-ins -------------------------------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    claim = {"place": "Los Angeles", "event": "house survived fire", "claimed_date": "January 2025",
             "period_start": "2025-01-07", "caption": "c"}
    monkeypatch.setattr(pipeline.claim, "read_claim", lambda caption, posted_on, budget=None: dict(claim))
    monkeypatch.setattr(pipeline.sam, "photo_regions", lambda b, budget=None: [])
    monkeypatch.setattr(pipeline.archive, "first_capture",
                        lambda url: {"date": "2023-08-24" if url.endswith(".jpg") else None,
                                     "snapshot": "https://web.archive.org/x", "ok": True})
    monkeypatch.setattr(pipeline.reader, "read_page", lambda url, imgs, budget=None: {
        "url": url, "opened": True, "title": "t", "relevant": True, "place": "Lahaina", "date": "2023-08-10",
        "event": "wildfire", "page_date": "2023-08-22", "quote": "q"})
    monkeypatch.setattr(pipeline.verdict, "judge", lambda *a, **k: {
        "verdict": "inconsistent", "cited": ["E1"], "summary": "Online in 2023.",
        "actual": {"place": "Lahaina", "date": "2023-08-10", "event": "wildfire"}})
    monkeypatch.setattr(pipeline.verdict, "critic", lambda *a, **k: {"approve": True, "problem": None})
    return monkeypatch


def run_events(**kw):
    return list(pipeline.run(jpeg(), "This house survived the LA fires", "2025-01-12", **kw))


def test_pipeline_catches_old_photo(offline):
    offline.setattr(pipeline.search, "google_vision", lambda b: {"pages": [
        {"url": "https://www.cbsnews.com/a", "title": "", "image_urls": ["https://cbs.com/a.jpg"], "match": "full"}],
        "best_guess": [], "similar": []})
    events = run_events()
    result = events[-1]
    assert result["type"] == "result"
    assert result["verdict"] == "inconsistent" and result["basis"] == "date rule"
    assert [t["date"] for t in result["timeline"]] == sorted(t["date"] for t in result["timeline"])
    assert {e["agent"] for e in events if e["type"] == "step"} >= {"claim", "search", "archive", "reader", "rule",
                                                                   "judge", "critic"}


def test_pipeline_with_no_copies_online_says_cannot_verify(offline):
    offline.setattr(pipeline.search, "google_vision", lambda b: {"pages": [], "best_guess": [], "similar": []})
    result = run_events()[-1]
    assert result["verdict"] == "cannot_tell" and result["basis"] == "no evidence"


def test_pipeline_reports_errors_as_events(offline):
    def boom(b):
        raise search.SearchUnavailable("reverse image search needs GOOGLE_VISION_API_KEY")
    offline.setattr(pipeline.search, "google_vision", boom)
    last = run_events()[-1]
    assert last["type"] == "error" and "GOOGLE_VISION_API_KEY" in last["text"]


def test_events_are_json_serialisable(offline):
    offline.setattr(pipeline.search, "google_vision", lambda b: {"pages": [
        {"url": "https://www.cbsnews.com/a", "title": "", "image_urls": ["https://cbs.com/a.jpg"], "match": "full"}],
        "best_guess": [], "similar": []})
    for e in run_events():
        json.dumps(e)


# Fixes from the code review ----------------------------------------------------------------------------------------

def test_judge_output_is_normalised():
    out = verdict._clean_judgement({"verdict": "maybe", "cited": [1, "E2", {"x": 1}, "E9"], "summary": None,
                                    "actual": "Lahaina"}, {"E1", "E2"})
    assert out["verdict"] == "cannot_tell" and out["cited"] == ["E2"] and out["summary"] == ""
    assert out["actual"] == {"place": None, "date": None, "event": None}
    assert verdict._clean_judgement({"verdict": "inconsistent", "cited": "E1, E2"}, {"E1", "E2"})["cited"] == ["E1", "E2"]


def test_model_booleans():
    assert meta.truthy(True) and meta.truthy("true") and not meta.truthy("false") and not meta.truthy(None)


@pytest.mark.parametrize("value,expected", [(2023, "2023"), ("2023-08", "2023-08"), ("2023-13-45", None),
                                            ("August 2023", None), (None, None)])
def test_described_dates_are_validated(value, expected):
    assert pipeline._iso(value) == expected


def search_one_page(monkeypatch, extra=None):
    pages = [{"url": "https://www.cbsnews.com/a", "title": "", "image_urls": ["https://cbs.com/a.jpg"],
              "match": "full"}] + (extra or [])
    monkeypatch.setattr(pipeline.search, "google_vision", lambda b: {"pages": pages, "best_guess": [], "similar": []})


def test_numeric_described_date_does_not_break_timeline(offline):
    search_one_page(offline)
    offline.setattr(pipeline.reader, "read_page", lambda url, imgs, budget=None: {
        "url": url, "opened": True, "relevant": True, "place": "Lahaina", "date": 2023, "event": "fire"})
    result = run_events()[-1]
    assert result["type"] == "result"
    assert any(t["kind"] == "described" and t["date"] == "2023" for t in result["timeline"])


def test_one_failing_page_does_not_end_the_check(offline):
    search_one_page(offline)

    def broken(url, imgs, budget=None):
        raise RuntimeError("Meta API call failed")
    offline.setattr(pipeline.reader, "read_page", broken)
    result = run_events()[-1]
    assert result["type"] == "result" and result["verdict"] == "inconsistent"  # the archive date still decides


def test_lookup_missing_from_recording_counts_as_no_data(offline):
    search_one_page(offline)

    def not_recorded(url):
        raise replay.NotInReplay("wayback")
    offline.setattr(pipeline.archive, "first_capture", not_recorded)
    result = run_events()[-1]
    assert result["type"] == "result" and result["rule"] is None, result


def test_same_page_from_two_search_images_keeps_the_full_match(offline):
    regions = [{"box": (0, 0, 10, 10), "conf": 0.9, "jpeg": jpeg()}]
    offline.setattr(pipeline.sam, "photo_regions", lambda b, budget=None: regions)
    answers = iter([
        {"pages": [{"url": "https://site.org/p", "title": "", "image_urls": ["https://site.org/crop.jpg"],
                    "match": "partial"}], "similar": []},
        {"pages": [{"url": "https://site.org/p", "title": "", "image_urls": ["https://site.org/full.jpg"],
                    "match": "full"}], "similar": []},
    ])
    offline.setattr(pipeline.search, "google_vision", lambda b: next(answers))
    result = run_events()[-1]
    (row,) = [e for e in result["evidence"] if e["url"] == "https://site.org/p"]
    assert row["match"] == "full"


def test_vision_error_is_not_turned_into_no_copies(replay_dir, monkeypatch):
    monkeypatch.setattr(config, "MODE", "live")
    monkeypatch.setattr(config, "GOOGLE_VISION_API_KEY", "test")

    class Answer:
        status_code = 200

        def json(self):
            return {"responses": [{"error": {"message": "Bad image data."}}]}
    monkeypatch.setattr(search.requests, "post", lambda *a, **k: Answer())
    with pytest.raises(search.SearchUnavailable):
        search.google_vision(jpeg())
    assert not any(replay_dir.rglob("*.json"))


def test_budget_cap_is_not_applied_to_replays(monkeypatch):
    monkeypatch.setattr(config, "MODE", "replay")
    b = meta.Budget(cap=0.0)
    b.check()


def test_claim_never_uses_todays_date(monkeypatch):
    seen = {}

    def fake(model, prompt, **k):
        seen["prompt"] = prompt
        return {"place": None, "period_start": 2024}, []
    monkeypatch.setattr(pipeline.claim.meta, "ask_json", fake)
    c = pipeline.claim.read_claim("Valencia yesterday", None)
    assert "The post was published on: unknown" in seen["prompt"]
    assert c["period_start"] is None


# Proof check ---------------------------------------------------------------------------------------------------------

CLAIM = {"period_start": "2025-01-07"}


def row(i, domain, **kw):
    return dict({"id": "E%d" % i, "domain": domain, "match": "full", "fact_checker": False}, **kw)


def test_grounds_accepts_a_copy_older_than_the_margin():
    g = verdict.grounds(CLAIM, [row(1, "a.com", image_first="2024-12-01")], {"cited": ["E1"]})
    assert g["ok"] and g["kind"] == "earlier copy"


def test_grounds_rejects_a_copy_only_days_older():
    g = verdict.grounds(CLAIM, [row(1, "a.com", page_published="2025-01-05T10:00")], {"cited": ["E1"]})
    assert not g["ok"]


def test_grounds_ignores_the_page_archive_date_and_partial_matches():
    ev = [row(1, "a.com", page_first="2010-01-01"), row(2, "b.com", match="partial", image_first="2010-01-01")]
    assert not verdict.grounds(CLAIM, ev, {"cited": ["E1", "E2"]})["ok"]


def test_grounds_needs_two_sites_describing_the_image():
    one = [row(1, "a.com", described_place="Turkey"), row(2, "a.com", described_place="Turkey")]
    assert not verdict.grounds({}, one, {"cited": ["E1", "E2"]})["ok"]
    two = [row(1, "a.com", described_place="Turkey"), row(2, "b.org", described_event="drill")]
    assert verdict.grounds({}, two, {"cited": ["E1", "E2"]})["kind"] == "independent descriptions"
    checker = [row(1, "a.com", described_place="Turkey"), row(2, "snopes.com", described_place="Turkey",
                                                             fact_checker=True)]
    assert not verdict.grounds({}, checker, {"cited": ["E1", "E2"]})["ok"]


def test_weak_proof_turns_into_cannot_tell(offline):
    offline.setattr(pipeline.archive, "first_capture", lambda url: {"date": None, "snapshot": None, "ok": True})
    offline.setattr(pipeline.reader, "read_page", lambda url, imgs, budget=None: {
        "url": url, "opened": True, "relevant": True, "place": "Turkey", "page_date": "2025-01-06"})
    search_one_page(offline)
    result = run_events()[-1]
    assert result["verdict"] == "cannot_tell" and result["basis"] == "proof too weak"

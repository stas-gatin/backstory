"""Build the track record: every post on X checked in Tests H2–H6, with its verdict and evidence, as text and links.

The result files of the tests stay local (runs/, they sit next to third-party media); this keeps what a reader needs
to check each verdict: the post link, what the fact-checker found, Backstory's verdict, its basis, the earliest copy
it cited, and whether the post had a Community Note. No media.

Usage:
  python -m eval.track_record      # writes eval/track_record.json
"""
import json
from pathlib import Path

from backstory import verdict

ROOT = Path(__file__).resolve().parent.parent
TESTS = [  # test, result file, version (commit), post set
    ("H2", "runs/test_h2.json", "ebc0c03", "eval/realset.json"),
    ("H3", "runs/test_h3.json", "c79bf8e", "eval/realset2.json"),
    ("H4", "runs/test_h4.json", "3bf7dfe", "eval/realset2.json"),
    ("H5", "runs/test_h5_v5.json", "ef47d1e", "eval/realset3.json"),
    ("H6", "runs/test_h6_v6.json", "d67e9e8", "eval/realset4.json"),
]


def first_copy(row):
    best = None
    for e in row.get("cited_rows") or []:
        d = verdict._first_dated(e)
        if d and (best is None or d < best["date"]):
            best = {"date": d, "domain": e.get("domain"), "url": e.get("url"),
                    "how": "image file archived" if d == e.get("image_first") else "published"}
    return best


def main():
    out = []
    for test, path, version, posts in TESTS:
        for r in json.load(open(ROOT / path))["posts"]:
            out.append({
                "test": test, "version": version, "set": posts, "group": r["group"], "media": r["media"],
                "post_url": r["post_url"], "claimed": r.get("claimed"), "truth": r.get("truth"),
                "fact_check": r.get("source_url"),
                "verdict": r["verdict"], "basis": r.get("basis"), "summary": r.get("summary"),
                "proof": (r.get("grounds") or {}).get("text"), "first_copy": first_copy(r),
                "community_note": bool(r.get("community_note")),
                # Right: a fake called "inconsistent". Wrong: a genuine post called "inconsistent". Otherwise the
                # check abstained ("cannot_tell") or confirmed a genuine post.
                "outcome": ("caught" if r["verdict"] == "inconsistent" else "missed") if r["group"] == "fake"
                else ("false alarm" if r["verdict"] == "inconsistent" else "no alarm"),
                "usd": round(r.get("usd") or 0, 3)})
    (ROOT / "eval" / "track_record.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(out), "posts")


if __name__ == "__main__":
    main()

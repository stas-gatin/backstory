"""The false captions Test E caught, one row each, for the Accuracy page (web/test_e.json).

    python -m eval.test_e_list          (needs data/5pils: git clone https://github.com/UKPLab/5pils data/5pils)

Claims, places and dates come from 5Pils (UKPLab, CC-BY-SA-4.0, https://github.com/UKPLab/5pils), shortened; the
earliest copy is what Backstory found in Test E (eval/feasibility/test_e_result.json). web/test_e.json is shared under
CC-BY-SA-4.0 too.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "test_e.json"


NE = "not enough information"
CHECKERS = {"pesacheck": "PesaCheck", "factly": "Factly", "211org": "211 Check"}


def place_date(place, date, n=90):
    date = re.sub(r"(\d{4}-\d\d-\d\d)T[\d:.+Z-]+", r"\1", date or "")      # 2022-10-21T12:03:33+00:00 -> 2022-10-21
    return short(" · ".join(v for v in (place, date) if v and v != NE), n)


def short(s, n=110):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def main():
    rows = json.load(open(ROOT / "eval/feasibility/test_e_result.json"))["rows"]
    by_url = {}
    for split in ("train", "val", "test"):
        for x in json.load(open(ROOT / "data/5pils/dataset" / (split + ".json"))):
            by_url[x["URL"]] = x
    out = []
    for r in rows:
        if r["false"]["AL"] != "inconsistent":
            continue
        x = by_url[r["url"]]
        first = min((e for e in r["evidence"] if e.get("img_first")), key=lambda e: e["img_first"], default=None)
        if first and first["img_first"] >= r["false"]["start"]:
            first = None                      # caught on what the pages say, not on an older copy
        out.append({"claim": short(x["claim"]), "claimed": place_date(x["claimed_location"], x["claimed_date"]),
                    "truth": place_date(x["location"], x["date"]), "checker": CHECKERS.get(x["org"], x["org"]), "fact_check": r["url"],
                    "first": first and {"date": first["img_first"], "domain": first["domain"].removeprefix("www.")},
                    "true_caption": r["true"]["AL"]})
    meta = {"source": "5Pils (UKPLab), CC-BY-SA-4.0, https://github.com/UKPLab/5pils; claims shortened",
            "test": "E", "cases": len(rows), "caught": len(out),
            "false_alarms": sum(r["true"]["AL"] == "inconsistent" for r in rows)}
    OUT.write_text(json.dumps({"meta": meta, "rows": out}, ensure_ascii=False, indent=1) + "\n")
    print(meta)


if __name__ == "__main__":
    main()

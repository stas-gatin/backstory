# Backstory

**Does the caption fit the photo's past?**

A photo goes viral with the caption "Valencia yesterday, after the DANA". Often the photo is real, but it was taken
years earlier or somewhere else. Pixels cannot reveal that. The photo's own history online can.

Backstory finds where this exact photo appeared on the web before and when, reads how those pages describe it,
and checks the caption against that record. Every verdict cites its evidence. With no record, the answer is
"cannot verify", never a guess.

> Status: in development for the Meta AI Developer Hackathon 2026 (26 Oct – 4 Nov 2026). Everything in this
> repository was written during the hackathon.

## Where to find what

| What | Where |
|---|---|
| The agents and how they hand work to each other | [`backstory/pipeline.py`](backstory/pipeline.py) |
| Claim reader (Muse Spark + web search) | [`backstory/claim.py`](backstory/claim.py) |
| Page reader (Muse Spark) | [`backstory/reader.py`](backstory/reader.py) |
| Date rule, judge (Muse Spark), critic (Muse Wonder) | [`backstory/verdict.py`](backstory/verdict.py) |
| Archivist (Internet Archive first captures) | [`backstory/archive.py`](backstory/archive.py) |
| Reverse image search | [`backstory/search.py`](backstory/search.py) |
| Record / replay of every external call | [`backstory/replay.py`](backstory/replay.py) |
| Evaluation on real fact-checked cases (5Pils) | [`eval/fivepils.py`](eval/fivepils.py) |
| The tests that decided this project, rules written first | [`docs/TESTS.md`](docs/TESTS.md) |

## How it works

| Step | Agent | Model or tool | What it does |
|---|---|---|---|
| 1 | Claim reader | Muse Spark + web search | Extracts place, event and date from the caption, in any language; resolves "yesterday" or a named event to a real date |
| 2 | Image search | Google Cloud Vision Web Detection | Finds pages that show this exact photo (Meta's API has no image search) |
| 3 | Archivist | Internet Archive (code) | First archived copy of each page and image file: proof it existed by that date |
| 4 | Page reader | Muse Spark | Reads each page: what place, date and event it gives for the photo |
| 5 | Date rule | code | If the image file was archived before the claimed date, the caption cannot be right |
| 6 | Judge | Muse Spark (sees the photo) | Weighs all evidence, must cite evidence ids |
| 7 | Critic | Muse Wonder | Checks the judge's citations; sends the judge back once; if still unconvinced, the answer is "cannot verify" |

Three possible answers: **fits**, **does not fit**, **cannot verify**.

## Measured so far

Test E ([docs/TESTS.md](docs/TESTS.md)): 105 real out-of-context images from 5Pils, each checked with the false caption
and with the true one, decision rule written before the run.

| | Caught false captions | False alarms on true captions |
|---|---|---|
| Date rule only (no model) | 49% | 1% |
| Muse Spark with the evidence | 67% | 8.6% |
| For comparison, Muse Spark with the photo only (Test D) | 3% | 28% |

Limits: the method needs earlier copies of the photo online. Counting the cases where reverse image search found
nothing, 41% of all false captions were caught. Fully fabricated or AI-generated photos have no past and get
"cannot verify".

## Run it

```bash
docker compose up --build
```

Then open http://localhost:8000. Without keys it runs in **replay mode**: recorded answers, no network, same results.
With keys (copy `.env.example` to `.env`) it runs live and records every new answer into `replay/`.

Evaluation on 5Pils:

```bash
git clone https://github.com/UKPLab/5pils data/5pils
python -m eval.fivepils --split val --limit 10
```

## Data and licences

- 5Pils (UKPLab, CC-BY-SA-4.0) is used for evaluation only; it is downloaded, not redistributed.
- Code: MIT.

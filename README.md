# Backstory

**Does the caption fit the photo's past?** Photos and videos.

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
| Reading a post on X from its link | [`backstory/xpost.py`](backstory/xpost.py) |
| Video frames and speech (Muse Voice Transcribe) | [`backstory/video.py`](backstory/video.py) |
| Photo finder for screenshots and collages (SAM 3.1) | [`backstory/sam.py`](backstory/sam.py) |
| Reverse image search | [`backstory/search.py`](backstory/search.py) |
| Match checker for look-alike images (Muse Spark, two images) | [`backstory/matcher.py`](backstory/matcher.py) |
| Archivist (Internet Archive first captures) | [`backstory/archive.py`](backstory/archive.py) |
| Page reader (Muse Spark) | [`backstory/reader.py`](backstory/reader.py) |
| Date rule, judge (Muse Spark), critic (Muse Wonder), proof check | [`backstory/verdict.py`](backstory/verdict.py) |
| Record / replay of every external call | [`backstory/replay.py`](backstory/replay.py) |
| Evaluation on real fact-checked cases (5Pils) | [`eval/fivepils.py`](eval/fivepils.py) |
| The tests that decided the design, rules written first | [`docs/TESTS.md`](docs/TESTS.md), [`docs/TEST_G.md`](docs/TEST_G.md), [`docs/TEST_H.md`](docs/TEST_H.md), [`docs/TEST_I.md`](docs/TEST_I.md) |

## How it works

| Step | Agent | Model or tool | What it does |
|---|---|---|---|
| 0 | Post reader | X embed data (no account) | From a link to a post on X: its text, date, photos or video. The post's Community Note, if any, is shown next to the verdict for comparison and never given to the agents |
| 0 | Frame grabber, speech reader | ffmpeg, **Muse Voice Transcribe** | Video posts only: four still frames to search for, and the words spoken in the clip |
| 1 | Claim reader | **Muse Spark** + web search | Extracts place, event and date from the caption, in any language; resolves "yesterday" or a named event to a real date. A post that presents media as news with no date ("first picture of…") is taken as no older than 30 days before the post |
| 2 | Photo finder | **SAM 3.1** | Cuts the separate photos out of a post screenshot or collage; each is searched along with the whole image |
| 3 | Image search | Google Cloud Vision Web Detection | Pages that show this photo (Meta's API has no image search) |
| 4 | Match checker | **Muse Spark** (two images) | When exact matches are scarce (video frames, re-encodes), compares look-alike images with the post and keeps only the same photo or footage |
| 5 | Archivist | Internet Archive (code) | First archived copy of each page and image file: proof it existed by that date |
| 6 | Page reader | **Muse Spark** | Reads each page: what place, date and event it gives for the photo |
| 7 | Date rule | code | If an exactly matching image file was archived before the claimed date, the caption cannot be right |
| 8 | Judge | **Muse Spark** (sees the photo) | Weighs all evidence, must cite evidence ids |
| 9 | Critic | **Muse Wonder** | Checks the judge's citations, and looks at cited look-alike images itself; sends the judge back once; if still unconvinced, the answer is "cannot verify" |
| 10 | Proof check | code | An approved "does not fit" must rest on proof the code can verify in the evidence table: a copy of the same image dated more than 7 days before the claim, or two different non-social sites describing it differently. Otherwise the answer becomes "cannot verify". The models propose; the code decides what counts as proof |

Three possible answers: **fits**, **does not fit**, **cannot verify**. A typical check makes 5–12 Muse Spark calls,
1–2 Muse Wonder calls and one SAM call, and costs about $0.05–0.10.

## Measured so far

**Test E** ([docs/TESTS.md](docs/TESTS.md)): 105 real out-of-context images from 5Pils, each checked with the false
caption and with the true one, decision rule written before the run. This measured the core method (archive dates +
Muse Spark reading the evidence), before the judge, critic and match checker existed.

| | Caught false captions | False alarms on true captions |
|---|---|---|
| Date rule only (no model) | 49% | 1% |
| Muse Spark with the evidence | 67% | 8.6% |
| For comparison, Muse Spark with the photo only (Test D) | 3% | 28% |

**Test G** ([docs/TEST_G.md](docs/TEST_G.md)): does a SAM 3.1 cut-out *instead of* the screenshot help reverse image
search? No (NO-GO, 17 cases): Google's partial matching already finds the photo inside a screenshot, and a wrong cut
loses it. SAM is therefore used only *in addition* to the whole image. On the same 17 cases (exploratory, not yet
confirmed on new data), adding SAM's cut-outs kept the hit rate (82%) and found 37% more of the photo's real copies
(225 vs 164 pages).

**Real viral posts** (checked live; the photos are not in this repository):

| Post | Backstory | Fact-checkers |
|---|---|---|
| "This house survived the Los Angeles wildfires" (Jan 2025) | Does not fit: published Aug 2023 as Lahaina, Maui | PolitiFact, VERA Files: Lahaina, 10 Aug 2023 |
| Morgue photo as hidden victims of the Valencia floods (Dec 2024) | Does not fit: in a San Diego Union-Tribune article from 2014 | Maldita: San Diego 2014 and Los Angeles 2016 |
| X video "hurricane Helene right now, storm surge 15-20ft" (Sep 2024) | Does not fit: same footage online by May 2024 (match confirmed by Spark and Wonder) | Lead Stories: Hurricane Ian, 2022 |

The prompts were adjusted while running these three, so they show that it works, not how often.

**The full pipeline on data it had not seen** ([docs/TEST_H.md](docs/TEST_H.md), [docs/TEST_I.md](docs/TEST_I.md)).
Each test's pass rule was committed before its run; each result is reported against that rule, including the
failures. A test is only run once; the next version is measured on new data.

| Test | Version | Data | Caught false captions | False alarms | Pre-registered rule |
|---|---|---|---|---|---|
| H1 | first full pipeline | 105 5Pils cases (Test E's) | 79% | **22.9%** | failed: false alarms > 10% |
| I | + proof check | 75 new 5Pils cases (train split) | 78.7% | **10.7%** | failed, narrowly: false alarms > 10% |
| H2 | + proof check | 53 real X posts, link only (mostly video) | 24% (6/25) | 3.6% (1/28) | no pass bar (sanity check) |
| H3 | + match checker for look-alikes | 39 fresh X posts | 22% (5/23) | 0% (0/16) | failed: caught < 35% |
| H4 | + implied date for news posts | 14 X posts no version had seen | 3 of 6 (all photos) | 0 of 8 | counts only (too small for a rate) |
| H5 | + post clock (dates of copies on X, TikTok, YouTube), A/B against H4's version | 56 fresh X video posts | 16% (5/31) vs 19% (6/31) | 0% (0/25) both | failed: no gain; no video rate claimed |

What the failures taught, one change each: H1's false alarms came from copies only days older than the claim and
from single pages, so the proof check was added (false alarms roughly halved in Test I). H3's misses were news posts
that give no date ("first picture of a chemical attack in Kursk", while the same photo was online in 2016): the
posting date is now the implied claimed date. On posts already seen, that change doubled the fakes caught on X
(H3: 5 → 12 of 23; H2: 6 → 12 of 25) with no false alarm; these are development numbers. On 14 posts it had not seen
(H4) it caught 3 of 6 fakes, all photos, with no false alarm; fake videos remain the weak spot. H5 tested a fix for
video on 56 fresh posts against the previous version: it did not help (5 vs 6 of 31 fakes, no false alarms either
way). Reverse image search on video frames finds nothing for a third of fake videos and nothing usable for most of
the rest, so Backstory catches fake videos only occasionally; it says "cannot verify" rather than guess.

Limits: the method needs earlier copies of the photo online. Counting the Test E cases where reverse image search
found nothing, 41% of all false captions were caught. Fully fabricated or AI-generated photos have no past and get
"cannot verify".

## Run it

```bash
docker compose up --build
```

Then open http://localhost:8000. Without keys it runs in **replay mode**: recorded answers, no network, same results.
With keys (copy `.env.example` to `.env`) it runs live and records every new answer into `replay/`.

Tests (offline, no keys, no network; every external call is replaced by a stand-in):

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests
```

Evaluation on 5Pils:

```bash
git clone https://github.com/UKPLab/5pils data/5pils
python -m eval.fivepils --split val --limit 10
```

## Data and licences

- 5Pils (UKPLab, CC-BY-SA-4.0) is used for evaluation only; it is downloaded, not redistributed.
- Photos and videos of the real cases above belong to their authors and are not included.
- Code: MIT.

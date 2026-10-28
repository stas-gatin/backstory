# Feasibility tests

Each test had its decision rule written down before any model call. Both are kept as they were written, with the result appended afterwards.

Test D asked whether a model can spot a false caption from the pixels alone (it cannot). Test E asked whether the photo's earlier appearances online catch real false captions (they do). Backstory is built on Test E.

## Test D: does the photo-context checker work on real misinformation? (written 2026-10-27, before any LLM call)

Budget: hard cap 0.30 USD of Meta API (estimated from returned token usage at 1.25 / 4.25 USD per million input /
output tokens; the run stops before a call that could pass the cap). One model call per claim, muse-spark-1.3,
reasoning effort "low", images downscaled to at most 768 px.

Data: 5Pils test split (UKPLab, CC-BY-SA-4.0), images of type "out-of-context" where the fact-checkers recorded the
claimed date, the claimed location, the true date and the true location. 30 cases drawn with a fixed seed (random.Random(4))
from those whose image URL downloads. Each case gives two claims about the same image:
FALSE = claimed location + claimed date (the real misinformation); TRUE = true location + true date (from the fact-check).

Arm B (model alone): Spark sees image + claim and returns a verdict (consistent / inconsistent / cannot_tell) and a list
of contradictions, each typed (time_of_day, weather, season, snow, language_or_signs, landmark_or_place, era_or_technology,
other) with what it saw (sun height, falling precipitation, snow on ground, deciduous foliage).
Arm A (model + checks): the same response, then code tests each physical contradiction (time_of_day, weather, season,
snow) against the solar elevation and the Open-Meteo ERA5 archive for the claimed place (Open-Meteo geocoding) and date.
A physical contradiction is REFUTED when the archive/sun data agree with the claim, and is dropped. Contradictions the
code cannot test (no day in the claim, place not geocoded, non-physical type) are kept as they are.
A verdict: inconsistent if at least one contradiction remains; cannot_tell if B said inconsistent and all its
contradictions were refuted; otherwise B's verdict.

Metrics per arm: detection = share of FALSE claims called inconsistent; false alarm = share of TRUE claims called
inconsistent ("cannot_tell" is not a false alarm). Also reported: applicability = share of FALSE claims where at least
one physical check could be run.

Decision:
1. Project viability (best arm): GO if detection >= 0.60 AND false alarm <= 0.20. NO-GO if detection < 0.40 OR
   false alarm > 0.30. Between: unclear, the user decides.
2. Physics checks as a headline feature: only if applicability >= 0.25 AND A false alarm <= B false alarm AND A loses
   at most 1 detection versus B. Otherwise physics checks are presented as a secondary tool, not the main claim.
Noted limitations: n = 30; the model may know famous images; fact-check dates are often only a year, so physics checks
may rarely apply.

## Result (2026-10-27)
Run stopped by the cost cap after 29 of 30 cases (58 calls, about 0.29 USD estimated from token usage).
Arm B: detection 0.03 (1 of 29), false alarm 0.28. Arm A: identical. Applicability of physics checks: 0.00
(the model listed no testable physical contradiction on any false claim).
Decision 1: NO-GO (detection < 0.40, false alarm > 0.30 not reached but detection fails). Decision 2: physics checks
not a headline feature.
Reading: real out-of-context claims mostly change the year or a nearby place, which the pixels do not reveal;
fact-checkers solve them by provenance (reverse image search), not by visual consistency. Test C's shifted-season
claims were much easier than real misinformation. Part of the false alarms may come from messy "true" descriptions
(several images, "various locations").

## Test E: can provenance ("this photo was online before the claimed event") catch real out-of-context claims?
(written 2026-10-27, before any LLM call and before any Wayback lookup on the test split)

Data: 5Pils test split, type "out-of-context", claimed date and true date known, at least one reverse-image-search
evidence entry in retrieval_results/evidence_urls.json, and a year parseable from the claimed date: 105 cases.
The val split (48 cases) is used only to debug code; no numbers from it are reported as results.
Coverage is also reported against all 172 eligible test cases (with or without evidence).

Evidence: the 5Pils reverse-search results (pages that show the image, and the image URLs on them). Leakage filter,
fixed now: drop evidence whose domain is a fact-checking site (factly.in, pesacheck.org, 211check.org, africacheck.org,
afp.com, boomlive.in, altnews.in, newschecker.in, thequint.com, vishvasnews.com, indiatoday.in, snopes.com,
reuters.com, factcheck.org, politifact.com, newsmobile.in, newsmeter.in, thelogicalindian.com, fullfact.org,
logicallyfacts.com, misbar.com, dubawa.org, faktisk.no) or whose URL matches
fact-?check|fake|hoax|misleading|false|debunk|verif. At most 10 image URLs and 5 page URLs per case.
Date of each evidence item: earliest Internet Archive (Wayback CDX) capture.

Claimed period start: the first full date in the claim text, else the first month + year (1st of month), else the
first year (1 January). Same parser for the true date.

Arm P (deterministic): inconsistent if any image URL's earliest capture is more than 1 day before the claimed period
start; else cannot_tell (P never says consistent).
Arm S (Muse Spark 1.3, reasoning low, image <= 768 px): image + claim + the filtered evidence list (domain, URL,
earliest capture date of page and image) -> consistent / inconsistent / cannot_tell.
Arm AL (Alibi): inconsistent if P fires, else S's verdict.
Reference (from Test D, image only): detection 0.03.

Metrics per arm on the 105 cases: detection on FALSE claims (claimed place + claimed date), false alarm on TRUE claims
(true place + true date); cannot_tell is not a false alarm.

Decision:
GO if AL detection >= 0.50 AND AL false alarm <= 0.10.
NO-GO if AL detection < 0.30 OR AL false alarm > 0.20.
Between: unclear, the user decides.
Also reported, not part of the rule: P versus S versus AL (does the Meta model add value over the deterministic check).
Budget: hard cap 3 USD for Spark calls (expected about 1.5 USD for 210 calls).
Limitations: Wayback captures only part of the web, so P has limited recall; reverse-search evidence was collected in
2023 by Google Vision, so a live product needs its own reverse image search; true dates in 5Pils are sometimes vague.

## Result (2026-10-27, 210 Spark calls, about 0.98 USD)
Wayback: 3 of about 830 lookups failed (counted as no capture). 78 of 105 cases had at least one dated image URL.
P (dates only): detection 0.486, false alarm 0.010.
S (Spark with evidence list): detection 0.667, false alarm 0.086.
AL (Alibi): detection 0.667, false alarm 0.086.
Decision: GO (AL detection >= 0.50 AND false alarm <= 0.10).
Against all 172 eligible test cases (cases without evidence count as missed): AL catches 70/172 = 0.41.
Observations, not part of the rule: Spark adds 19 catches the date rule misses, and brings 8 of the 9 false alarms
(mostly cases with no dated image evidence). One P false alarm: image archived in 2019 while the 5Pils true date is
2023, which points to a vague or wrong true date in the dataset.

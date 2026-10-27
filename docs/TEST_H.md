# Test H: does the full Backstory pipeline hold up on cases it was not tuned on?

Written 2026-10-27, before any pipeline run for this test. The prompts were tuned on five live cases (Lahaina,
the morgue screenshot, the Helene video, two Valencia posts), so those numbers are not evidence. Test H measures the
current pipeline (claim reader, Vision or recorded search, match checker, archivist, page reader, date rule, judge,
critic with one send-back) on data it has not seen. The result is appended below, whatever it is.

## H1: the Test E cases through the full pipeline

Data: the same 105 cases of the 5Pils test split as Test E (out-of-context images, claimed and true date known, at
least one recorded reverse-search result, a year in the claimed date). The same image files as Test E
(`data/5pils_e_test/NNN.jpg`, NNN = case index in `eval.fivepils.load_cases`), the same recorded search results and
the same leakage filter (fact-checking sites and URLs matching `fact-?check|fake|hoax|misleading|false|debunk|verif`
removed). Test E's Internet Archive lookups are reused (imported into the replay store), so archive dates are the
same; URLs Test E did not look up are looked up live.

Each case is checked twice, with the caption "Photo taken in <place>, <date>." built from the claimed place and
date (false) and from the true place and date (true). Posting date "unknown". Fact-checking pages are excluded.
Pages are read live, so pages that changed or disappeared since 2023 give less evidence than they did then.

Metrics: detection = share of false captions called "inconsistent"; false alarm = share of true captions called
"inconsistent" ("cannot_tell" is not a false alarm). Also reported: share of "cannot_tell" in each group, errors,
cost, and the same metrics for the date rule alone.

Reference (Test E, simple version: date rule + one Spark call): detection 0.667, false alarm 0.086.

Claims allowed afterwards:
- "keeps the Test E level" only if detection >= 0.60 and false alarm <= 0.086;
- "the judge and critic cut false alarms" only if false alarm <= 0.043 and detection >= 0.55;
- if detection < 0.55 or false alarm > 0.10: the current pipeline is worse than Test E's simple version on this data,
  and this is said in the README.
Errors (a check that did not finish) count as not detected for false captions and not a false alarm for true ones.

Budget: hard cap 14 USD for H1 (the run stops before starting a check once spent >= cap).

## H2: real posts on X, link only

Data: posts collected for this test (2026-10-27) and frozen as `eval/realset.json` before any pipeline run on them:
- "fake": a real photo or video posted on X with a false place/date/event caption, debunked by a professional
  fact-checker (no AI-generated or edited media);
- "true": posts by news organisations or official accounts with a photo or video and a correct caption, posted
  within 2 days of the event.
Only posts still available without login are kept. The five posts used to tune the prompts are excluded.

Input: the post link only. Backstory reads the text, date and media itself. Live Google Vision search; fact-checking
sites and debunk-looking URLs (same regex as H1) are removed from the search results. The X Community Note is never
given to the agents (it is only shown next to the verdict in the app).

Reported: detection (fake), false alarm (true), share of "cannot_tell", photo vs video, cost. No pass threshold:
the set is small and was collected by search, so it is a sanity check on real posts, not a benchmark.

Budget: hard cap 6 USD for H2.

## Limits
- 5Pils pages and images changed since 2023; H1 may come out lower than Test E for that reason alone.
- H2 is small; "true" posts come from news organisations, which are easier than ordinary users' posts.
- Both use Google Vision for search (Meta's API has no image search).

## H2 set, frozen 2026-10-27 before any H2 run
Collected by search in about one hour (Full Fact, Lead Stories and Newschecker debunks that name the X post; news and
official accounts for "true"). 54 posts passed the availability check. One is dropped before the run because the
fact-checker says shared copies of the clip were mirrored or cropped (edited media is outside the test): 53 posts,
`eval/realset.json` (25 fake, 28 true; 24 + 1 and 22 + 6 video + photo). Known weak points, kept as they are:
two fakes without an exact true origin, one parody account, one fake whose place is partly in on-screen text, two
true captions with a small error (a weekday; a region instead of the island), and five true posts that are the
originals of footage used in fakes in the set (pairs on the same media, so not independent).

## H1 result (2026-10-27, pipeline at commit 73ce957, 11.76 USD)
105 cases, 210 checks, 1 error (a false caption).

| | false captions | true captions |
|---|---|---|
| "inconsistent" | 83 (detection 0.790) | 24 (false alarm 0.229) |
| "cannot_tell" | 20 | 51 |
| "consistent" | 1 | 30 |

Date rule alone: detection 0.486, false alarm 0.000 (Test E: 0.486 / 0.010).

Decision under the rule above: false alarm 0.229 > 0.10, so **the pipeline at this commit is worse than Test E's
simple version on this data** (more catches, 0.790 vs 0.667, but far more false alarms, 0.229 vs 0.086).
All 24 false alarms came from the judge, approved by the critic; none from the date rule.

Reading (after the result, not part of the rule): in the false alarms the judge treated a copy published a few
days before the claimed date, or a single page describing the image differently, as proof. Several "true" dates in
5Pils are when the image was first found or published, not when it was taken, so an older copy is not always an
error of the pipeline; that is a property of the data and is not used to excuse the number.

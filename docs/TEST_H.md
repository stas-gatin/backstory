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

## H2 result (2026-10-28, pipeline at commit ebc0c03 with the proof check, 3.39 USD)
H2 was first started on 73ce957 and stopped after 17 posts when the proof check was added; it was rerun in full on
ebc0c03 (recorded searches and video frames reused). Results of the full rerun, 53 posts:

| | fake (25: 24 video, 1 photo) | true (28: 22 video, 6 photo) |
|---|---|---|
| "inconsistent" | 6 (0.24) | 1 (0.036) |
| "cannot_tell" | 19 | 26 |
| "consistent" | 0 | 1 |

Reading: on real X posts, nearly all video, the pipeline rarely catches the fake (0.24) but almost never raises a
false alarm. Misses: 4 posts with no search result at all; most others had only "partial" matches from video
frames, which the judge rightly does not trust; three caught by the judge were stopped by the proof check because
the evidence was a single page or only partial matches. The one false alarm disagreed with the caption only on a
detail of the event in the same city on the same day.

## H3: a fresh set of real X posts for the next version (written 2026-10-28, before any run on these posts)
After H2, the pipeline was changed (commit c79bf8e), looking at H2's misses: partial matches are compared with the
frame or photo they were found for by the match checker (Muse Spark) and count as the same source only when
confirmed; pages that place the image in the claimed place and do not date it earlier no longer count as proof;
social and video sites no longer count as independent descriptions; more fact-checking sites are excluded.
H2 can no longer measure this fairly, so a new set was collected the same way (about one hour of search, another
agent run, all earlier posts excluded): 55 posts available without login. Two are dropped before the run because
the false part is who is pictured, not the place, date or event: 53 posts, `eval/realset2.json` (29 fake: 17 photo,
12 video; 24 true: 14 photo, 10 video), shuffled with a fixed seed so that a run stopped by the cost cap is still a
random subset. Same input rules as H2 (link only, fact-checkers and debunk-looking URLs removed, Community Note
never given to the agents).

Claims allowed afterwards (on the posts checked):
- "the new version catches more fakes on real posts" only if detection >= 0.35 and false alarm <= 0.10
  (H2 on the earlier version: 0.24 and 0.036);
- if false alarm > 0.10: the new version is not ready for real posts, and the README says so.
Budget: hard cap 3 USD (the total for all tests stays at about 40 USD).

## H3 result (2026-10-28, pipeline at commit c79bf8e, 3.12 USD)
The 3 USD cap stopped the run after 39 of the 53 shuffled posts (23 fake: 14 photo, 9 video; 16 true: 10 photo,
6 video). One fake photo ended in an error (Google Vision returned a server error).

| | fake (23) | true (16) |
|---|---|---|
| "inconsistent" | 5 (0.217) | 0 (0.000) |
| "cannot_tell" | 17 | 11 |
| "consistent" | 0 | 5 |
| error | 1 | 0 |

By media: fake photos 5 of 14 (0.357), fake videos 0 of 9.

Decision under the rule above: detection 0.217 < 0.35, so **the claim "the new version catches more fakes on real
posts" is not supported**. False alarm 0.000 <= 0.10, so the new version raises no false alarm on this set.

Reading (after the result, not part of the rule): six posts had no reverse-search result at all. Three fakes were
caught by the judge and approved by the critic but stopped by the proof check. In two of them the evidence was a
copy published long before the post (rainews.it, May 2024, for a post of Feb 2026; Al-Alam, Nov 2016, for a post
of Aug 2024), but the caption gave no date ("Iran launching missiles from beneath the sea"; "First picture of a
chemical attack in Kursk"), so there was no claimed date for an earlier copy to beat. A post that presents media as
news implies "now"; the pipeline did not use the posting date as that implied date.

## H4: the 14 posts of the H3 set that the cost cap left unchecked (written 2026-10-28, before any run on them)
After H3 the claim reader was changed (commit 3bf7dfe), looking at H3's misses: when a caption presents the media as news
("breaking", "first picture of", "just landed") and gives no date, the posting date minus 30 days is taken as the
earliest date of the claimed scene, so a copy shown to exist earlier than that counts against the caption (with
the usual 7-day margin in the proof check). On the posts already seen (development numbers, not a result): H3's 39
posts went from 5 of 23 fakes caught to 12 of 23, with 0 of 16 false alarms; H2's 53 posts from 6 of 25 to 12 of 25,
with 0 of 28 false alarms.

Data: the posts of `eval/realset2.json` at positions 39–52 (the shuffled order fixed before H3), which no pipeline
version has been run on: 14 posts, 6 fake (3 photo, 3 video), 8 true (4 photo, 4 video). Same input rules as H2 and H3.

Claims allowed afterwards: with 6 fakes and 8 true posts, no rate is reliable; the counts are reported as they are,
and also pooled with H3 for the version at c79bf8e (39 posts) and 3bf7dfe (14 posts) separately, never merged into one
number for one version. If any true post is called "inconsistent", the README says so.

Budget: hard cap 2 USD.

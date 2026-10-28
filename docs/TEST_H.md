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

## H4 result (2026-10-28, pipeline at commit 3bf7dfe, 0.94 USD)
All 14 posts checked, no errors.

| | fake (6: 3 photo, 3 video) | true (8: 4 photo, 4 video) |
|---|---|---|
| "inconsistent" | 3 (all three photos) | 0 |
| "cannot_tell" | 3 (all three videos) | 7 |
| "consistent" | 0 | 1 |

No true post was called "inconsistent". The three caught fakes rest on earlier originals, none on a debunk: a 2019
VOA/in.gr photo of a German army ceremony shown as an Iranian raid in 2024; a bridge photo archived in 2024 shown as
a November 2025 collapse; a gazeta.ru photo archived in 2014 shown as Moscow in the dark in 2024. Two fake videos had
no reverse-search result; the third had one page only, on x.com. On one true photo (Kentucky flood, 2022) the judge
and critic agreed on "inconsistent" from two YouTube partial matches; the proof check stopped it ("proof too weak").
Speech was transcribed in 3 of 7 videos; it did not change any verdict.

Pooled with H3 by version, as pre-registered: c79bf8e on 39 posts caught 5 of 23 fakes with 0 of 16 false alarms;
3bf7dfe on 14 posts caught 3 of 6 fakes with 0 of 8 false alarms. The samples are too small for a rate.

## H5: fresh video posts, version 4 against version 5 (written 2026-10-28, before any run on these posts)
After H4, fake videos were the weak spot. Reverse search finds most copies of a video on YouTube, X and TikTok, and
the pipeline did not date them. Version 5 (commit ef47d1e) adds a post clock (code, no model): the posting date of a
copy on X or TikTok is read from its post id, on YouTube from the page's metadata; copies posted before the claimed
date are compared with the post's frames by the match checker using their cover image (in their own places, so they
never push out other partial matches), and a confirmed one counts as an earlier copy. Cover images are never dated by
the Internet Archive (a first attempt did that and produced 8 false alarms on development posts; fixed, with a test).
On the video posts already seen (H2, H3, H4: 36 fake, 32 true) version 5 caught 16 fakes against version 4's 15,
with 0 false alarms for both: development numbers, not a result.

Data: `eval/realset3.json`, collected for this test by an agent the same way as before (about 75 minutes; all
earlier posts excluded; every post available without login with a video): 57 posts, one dropped before the run
because the fact-checker's dates for it do not agree: 56 posts, 31 fake and 25 true, all video, shuffled with a fixed
seed. Unlike earlier sets, the true posts were found through fact-check articles that cite them as the original of
footage later misused, and three true posts are the originals of fakes in the set.

Both versions run on all 56 posts with the same input rules as H2–H4 and share one record store, so they see the same
search results, frames and pages; only the post clock differs. Version 5 runs first.

Claims allowed afterwards:
- "the post clock catches more fake videos" only if version 5 catches more fakes than version 4 and calls no more
  true posts "inconsistent";
- "Backstory catches fake videos on X" with a rate only if version 5's detection >= 0.35 and false alarm <= 0.10;
- if version 5's false alarm > 0.10, the README says the post clock is not ready.
Budget: hard cap 8 USD for version 5 and 6 USD for version 4.

## H5 result (2026-10-28; version 5 at ef47d1e, 4.64 USD; version 4 at 3bf7dfe, 4.31 USD with shared records)
All 56 posts checked by both versions, no errors.

| | version 4 | version 5 (post clock) |
|---|---|---|
| fake videos called "inconsistent" (31) | 6 (0.194) | 5 (0.161) |
| true videos called "inconsistent" (25) | 0 | 0 |
| true videos called "consistent" | 2 | 2 |

The versions differ on one post only (a church fire in Yorkshire): version 4 caught it through the date rule on an
archived partial-match image; in version 5 the match checker confirmed that page as the same footage, the page's
image was then not archive-dated, and the judge's "inconsistent" was stopped by the proof check.

Decision under the rule above: version 5 does not catch more fakes than version 4, so **the claim "the post clock
catches more fake videos" is not supported**. Detection 0.161 < 0.35, so **no detection rate for fake videos on X is
claimed**. False alarm 0.000 for both. The post clock stays in the pipeline (it shows the exact date of each copy on
X, TikTok and YouTube and never raised a false alarm), but it is not presented as an improvement.

Why fake videos are missed (version 5, 26 misses): 10 had no reverse-search result for any frame; 13 had pages, but
nothing the judge could use (copies with no date earlier than the claim, or only unconfirmed partial matches); 3 had
a sign against the caption that did not meet the proof check.

## H6: scene witness on fresh video posts, version 6 against version 5 (written 2026-10-28, before any run on them)
After H5, a new agent (commit d67e9e8): Muse Spark watches the whole video (first 60 s, 720p, 2 frames per second; or the
photo) and lists text readable in the filmed scene, with the second it appears, landmarks, and up to three moments
that best identify the footage. Those moments are searched as extra frames. Each scene text that names a place is
checked by Muse Wonder on its own frame: visible word for word, part of the scene (not an overlay), naming another
country than the caption, and impossible at the claimed place (flags, placards, adverts, chain stores, departure
boards and places inside or bordering the claimed one do not count). Only such a confirmed text is accepted by the
proof check as "the scene itself" contradicting the caption. The switch `BACKSTORY_WITNESS=0` turns the agent off,
which gives version 5.

Development (posts already seen, H2–H5: 85 fake, 77 true): video fakes caught 26 of 67 against 20; photo fakes 11
of 18 against 12; 0 false alarms in both. A first version raised one false alarm (a Vatican inscription in a Rome
video read as "another country"); the check was made stricter (question 5 above) before this pre-registration.

Data: `eval/realset4.json`, collected for this test by an agent (about 75 minutes, all earlier posts excluded,
every post available without login with a video). 47 found; two dropped before the run because they are compilations
of several unrelated clips: 45 posts, 23 fake and 22 true, all video, shuffled with a fixed seed. Most true posts
come from news, agency and official accounts embedded in live blogs; 6 are originals cited by fact-checks, and four
pairs share footage.

Both versions run on all 45 posts with the same input rules and one shared record store; version 6 runs first.
Claims allowed afterwards:
- "the scene witness catches more fake videos" only if version 6 catches more fakes than version 5 and calls no
  more true posts "inconsistent";
- a detection rate for fake videos only if version 6's detection >= 0.35 and false alarm <= 0.10;
- if version 6's false alarm > 0.10, the README says the scene witness is not ready.
Budget: hard cap 8 USD for version 6 and 5 USD for version 5.

## H6 result (2026-10-28; version 6 at d67e9e8, 4.67 USD; version 5, same code with the witness off, 3.51 USD)
All 45 posts checked by both versions, no errors.

| | version 5 | version 6 (scene witness) |
|---|---|---|
| fake videos called "inconsistent" (23) | 1 (0.043) | 1 (0.043) |
| true videos called "inconsistent" (22) | 0 | 0 |
| true videos called "consistent" | 2 | 4 |

Both versions caught the same single fake (a clip posted on X in April 2020, shown as Kabul airport in August 2021).
The witness added distinctive moments to the search for 36 of 45 videos, but they found no earlier copy; it
confirmed a place-naming sign in the scene for 2 posts, both true and both in the claimed country.

Decision under the rule above: version 6 does not catch more fakes than version 5, so **the claim "the scene witness
catches more fake videos" is not supported**; detection 0.043 < 0.35, so **no detection rate for fake videos is
claimed**. No false alarm in either version. This set was much harder than the development posts (1 of 23 fakes for
both versions, against 20–26 of 67 on development posts): 7 fakes had no reverse-search result at all and 12 had
pages that gave the judge nothing usable. The scene witness stays in the pipeline (it raised no false alarm and it
gives the reader the signs it can read), but it is not presented as an improvement in detection.

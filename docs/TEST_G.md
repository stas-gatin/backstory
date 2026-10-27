# Test G: does SAM 3.1 make reverse image search work on screenshots of posts?

Written 2026-10-27, before any SAM call on this data and before any image search on the screenshots.

**Question.** People rarely have the clean photo; they have a screenshot of a post (account name, text, buttons,
sometimes a banner over the image). Does cutting the photo out with SAM 3.1 before reverse image search find the
photo's earlier copies more often than searching the screenshot as it is?

**Data.** The 105 images of Test E (5Pils test split, out-of-context, already downloaded, at most 768 px), in file
order. Eligible: Google Vision Web Detection on the image itself returns at least one page with a full match.
The first 60 eligible images are used (fewer if fewer are eligible).

**Screenshots (synthetic, made by `eval/screenshots.py`, fixed seed 7).** Each image is placed in a generic post
layout 1080 px wide: a header with a round avatar, a made-up account name and a time; two to four lines of post text
above the photo; the photo scaled to 1000 px wide; a footer row with reaction icons and counts. Even-numbered cases
also get a banner of large white text with a black outline across the top 18% of the photo ("BREAKING" style).
The screenshot is saved as JPEG quality 80. The photo's exact position is recorded.

**Arms (one Vision search each).**
- S: the screenshot as it is.
- M: SAM 3.1 with the single fixed prompt "photo"; the highest-confidence box is cropped from the screenshot. If SAM
  returns no box, M uses the screenshot (counted as a SAM miss).
- O: the original image (upper bound, also the eligibility search).

**Metrics.**
- Hit rate per arm: share of cases where the search returns at least one page that also appears in O's page list
  (same URL). This asks "does it find the photo's real copies".
- Crop quality: IoU of SAM's box with the recorded photo position; share of cases with IoU >= 0.9.
- Also reported: mean number of full-match pages per arm; results for plain and banner cases separately.

**Decision.**
- GO (SAM goes into the pipeline before search) if hit(M) >= hit(S) + 0.15 AND hit(M) >= 0.8 x hit(O).
- NO-GO if hit(M) <= hit(S) + 0.05.
- Between: unclear, the user decides.

**Amendment (2026-10-27, still before any SAM call or screenshot search).** A first look at the generated
screenshots showed that many 5Pils images are themselves screenshots of posts, with text above the photo. SAM may then
correctly cut out the inner photo, which gives a low IoU against the recorded position although the crop is better.
So IoU is reported but removed from the decision (it was: NO-GO if IoU >= 0.9 in fewer than 60% of cases).

**Budget.** SAM: at most 60 images x 2.50 USD / 1000 = 0.15 USD. Vision: about 240 requests, within the free
1000 per month. Hard cap in code: 0.50 USD for SAM.

**Limits.** Screenshots are synthetic: real ones vary more (dark mode, stickers, several photos). The banner covers
part of the photo, so even a perfect crop keeps it. Matching by exact URL undercounts hits (same page, other URL).

## Result (2026-10-27, 17 cases, SAM 0.04 USD)

Only 17 of the 105 images were eligible: most no longer have a full match online (pages and files removed since
2023), so n is small.

| Arm | Finds the photo's real copies (hit) | Full-match pages, mean |
|---|---|---|
| S: screenshot as is | 0.824 | 0.00 |
| M: SAM cut-out ("photo") | 0.647 | 3.65 |
| O: original image | 1.000 | 2.76 |

Plain screenshots: S 0.875, M 0.875. With banner: S 0.778, M 0.444. SAM returned no box for 2 of 17; no box reached
IoU 0.9 with the recorded photo position (many 5Pils images are themselves screenshots, see the amendment).

**Decision: NO-GO** (hit(M) <= hit(S) + 0.05). SAM does not go in front of the search.

Observation, not part of the rule: searching the screenshot never returns full matches but Google's partial
matching still finds the right pages; SAM's crop brings back full matches when the cut is right, and loses the
photo when it cuts the wrong region (most often with the banner). Searching both and merging was not tested.

# Test I: the fixed pipeline on cases it has never seen

Written 2026-10-28, before any pipeline run on these cases. Pipeline frozen at commit ebc0c03.

Why: Test H1 showed that the pipeline at 73ce957 raised too many false alarms (0.229). The fix (the proof check:
an approved "does not fit" must rest on a copy of the same image dated more than 7 days before the claim, or on
at least two independent sites describing it differently, verified by code; and the judge's prompt says so) was
developed by looking at the H1 cases, so H1 can no longer measure it fairly. On H1's cases (69 of 105 before its
8 USD cap) the fixed pipeline gave detection 0.812 and false alarm 0.116; those numbers are development numbers, not
a result.

Data: 5Pils **train** split, which no Backstory code or prompt has been run on. Same eligibility as Test E
(out-of-context, claimed and true date known, recorded reverse-search results, a year in the claimed date): 129
cases. A fixed random sample of 100 (`random.Random(11)`, `eval.fivepils --split train --sample 100`); all 100
images downloaded. Same leakage filter, captions ("Photo taken in <place>, <date>."), posting date "unknown",
fact-checking sites excluded. Internet Archive lookups and pages are live.

Main set (fixed now, mechanically): the 75 of the 100 cases whose true date is a plain date. Cases are left out of
the main set when the true date text matches
`publish|found|first|shared|upload|image|photo|or\b|between|before|after|unknown|\?` or has no year, because those
texts are not a date the photo was taken ("Before 2017", "First photo: ...; Second photo: ...", "Found online in
September 2020"), so a caption built from them cannot be checked as true or false. All 100 are also reported.

Metrics: detection (false captions called "inconsistent"), false alarm (true captions called "inconsistent"),
"cannot_tell" shares, errors (count as not detected / not a false alarm), date rule alone, cost.

Claims allowed afterwards, on the main set:
- "the fix works on new data" only if false alarm <= 0.10 and detection >= 0.60;
- "better than Test E's simple version" only if, in addition, detection >= 0.667 and false alarm <= 0.086;
- if false alarm > 0.10 or detection < 0.55: the pipeline still raises too many false alarms or misses too much,
  and the README says so.

Budget: hard cap 13 USD.

Limits: one dataset (5Pils, fact-checks from 2020–2023, many from Africa and South Asia); pages changed since 2023;
the true dates are the fact-checkers' and can themselves be wrong.

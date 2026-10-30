# Feasibility test scripts (as run on 27 Oct 2026)

These are the scripts behind the two tests in [docs/TESTS.md](../../docs/TESTS.md), kept unchanged so the numbers
can be traced. They came before the app and are not part of it.

- `pick_d.py`, `run_d.py`: Test D (can a model spot a false caption from the pixels alone; NO-GO).
- `prefetch_e.py`, `run_e.py`: Test E (does provenance catch real false captions; GO).
  `test_e_result.json` holds every case, evidence date and verdict.
- `samclient.py`, `check_c.py`: helpers they import (API client, JSON parsing, solar elevation).

They expect the 5Pils dataset in `data/5pils` and a `MODEL_API_KEY`. Run them from this folder.

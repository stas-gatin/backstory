"""Settings read from the environment (and from a local .env file, if there is one)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v.strip() and not os.environ.get(k.strip()):
            os.environ[k.strip()] = v.strip()


_load_dotenv()

MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "")
GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "")

# live: call the real services and record every answer into replay/.
# replay: answer only from replay/ (no keys, no network). Used by the public demo and by judges.
MODE = os.environ.get("BACKSTORY_MODE") or ("live" if MODEL_API_KEY else "replay")
REPLAY_DIR = Path(os.environ.get("BACKSTORY_REPLAY_DIR", ROOT / "replay"))

META_API = "https://api.meta.ai/v1/responses"
SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"

# USD per million tokens (input, output). Used only to report and cap spending.
PRICES = {SPARK: (1.25, 4.25), WONDER: (4.0, 20.0)}  # dev.meta.ai pricing page, 2026-10-27
COST_CAP_PER_CHECK = float(os.environ.get("BACKSTORY_COST_CAP", "0.30"))

MAX_PAGES = 6          # pages the reader agent opens per photo
MAX_ARCHIVE_LOOKUPS = 12
MAX_SIMILAR = 8        # look-alike images the match checker compares when exact matches are scarce

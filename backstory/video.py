"""Video posts: the spoken claim (Muse Voice Transcribe) and a few still frames to search for.

A viral video often makes its claim out loud ("this is Florida right now"), and its frames can be searched like
photos: an old clip has old copies online too.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import requests

from . import config, replay

ASR_URL = "https://api.meta.ai/v1/asr/transcribe"
ASR_MODEL = "muse-voice-transcribe-1.0"
ASR_USD_PER_HOUR = 0.18
MAX_AUDIO_S = 600  # the API takes at most 10 minutes


class VideoError(Exception):
    pass


def _run(args):
    p = subprocess.run(args, capture_output=True, timeout=180)
    if p.returncode != 0:
        raise VideoError("the file is damaged or not a video format Backstory can read")
    return p.stdout


def duration(path):
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


def frames(path, n=4):
    """n JPEG frames spread over the video (at 10%, 35%, 60%, 85% for n=4)."""
    d = duration(path)
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = d * (0.1 + 0.75 * i / max(1, n - 1))
            f = Path(tmp) / ("f%d.jpg" % i)
            _run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", str(path), "-frames:v", "1",
                  "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", "-y", str(f)])
            if f.exists():
                out.append({"t": round(t, 1), "jpeg": f.read_bytes()})
    return out


def audio_wav(path):
    """16 kHz mono WAV of the first 10 minutes, or None if the video has no sound."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "a.wav"
        try:
            _run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-t", str(MAX_AUDIO_S),
                  "-acodec", "pcm_s16le", "-y", str(f)])
        except VideoError:
            return None
        return f.read_bytes() if f.exists() and f.stat().st_size > 1000 else None


def transcribe(wav, budget=None):
    """Spoken words in the clip (Muse Voice Transcribe), or "" if nothing was said."""
    sha = hashlib.sha256(wav).hexdigest()

    def fetch():
        r = requests.post(ASR_URL, headers={"Authorization": "Bearer " + config.MODEL_API_KEY,
                                            "Accept": "application/json"},
                          files={"request": (None, json.dumps({"model": ASR_MODEL, "audioEncoding": "WAV",
                                                               "mode": "PUSH_TO_TALK"}), "application/json"),
                                 "audio": ("clip.wav", wav, "audio/wav")}, timeout=300)
        r.raise_for_status()
        return r.json()

    j = replay.cached("asr", {"audio_sha256": sha, "model": ASR_MODEL}, fetch, note="speech")
    if budget:
        budget.add_usd(ASR_MODEL, j.get("audioDurationMs", 0) / 3.6e6 * ASR_USD_PER_HOUR)
    return (j.get("transcript") or "").strip()

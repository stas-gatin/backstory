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
    try:
        out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
        return float(json.loads(out)["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise VideoError("the video has no readable length")


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _grab(path, t):
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "f.jpg"
        _run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", str(path), "-frames:v", "1",
              "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", "-y", str(f)])
        return f.read_bytes() if f.exists() else None


def frames(path, n=4):
    """n JPEG frames spread over the video (at 10%, 35%, 60%, 85% for n=4).

    Recorded by the video file's hash, not by the decoded bytes: another ffmpeg version decodes slightly
    differently, which would otherwise make recorded searches miss."""
    sha = file_sha(path)
    d = replay.cached("videoinfo", {"video_sha256": sha}, lambda: {"duration": duration(path)})["duration"]
    out = []
    for i in range(n):
        t = d * (0.1 + 0.75 * i / max(1, n - 1))
        jpeg = replay.cached_bytes("frame", {"video_sha256": sha, "i": i, "n": n}, lambda: _grab(path, t))
        if jpeg:
            out.append({"t": round(t, 1), "jpeg": jpeg})
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


def speech(path, budget=None):
    """Spoken words in the video (Muse Voice Transcribe), or "" if there is no sound or nothing was said.
    Recorded by the video file's hash, for the same reason as frames()."""

    def fetch():
        wav = audio_wav(path)
        if wav is None:
            return {"transcript": "", "audioDurationMs": 0}
        r = requests.post(ASR_URL, headers={"Authorization": "Bearer " + config.MODEL_API_KEY,
                                            "Accept": "application/json"},
                          files={"request": (None, json.dumps({"model": ASR_MODEL, "audioEncoding": "WAV",
                                                               "mode": "PUSH_TO_TALK"}), "application/json"),
                                 "audio": ("clip.wav", wav, "audio/wav")}, timeout=300)
        if r.status_code != 200:
            return {"failed": True}
        return r.json()

    j = replay.cached("asr", {"video_sha256": file_sha(path), "model": ASR_MODEL}, fetch, note="speech",
                      keep=lambda r: not r.get("failed"))
    if budget:
        budget.add_usd(ASR_MODEL, j.get("audioDurationMs", 0) / 3.6e6 * ASR_USD_PER_HOUR)
    if j.get("failed"):
        return None
    return (j.get("transcript") or "").strip()

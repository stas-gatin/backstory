"""Client for Meta's Model API (Responses API): Muse Spark and Muse Wonder."""
import base64
import io
import json
import threading
import time

import requests
from PIL import Image

from . import config, replay


class Budget:
    """Token use and estimated cost of one check; stops before a call that would pass the cap."""

    def __init__(self, cap=config.COST_CAP_PER_CHECK):
        self.cap = cap
        self.usd = 0.0
        self.calls = {}
        self._lock = threading.Lock()

    def add(self, model, usage):
        pin, pout = config.PRICES.get(model, (5.0, 20.0))
        cost = (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1e6
        with self._lock:
            self.usd += cost
            self.calls[model] = self.calls.get(model, 0) + 1

    def add_usd(self, model, usd):
        with self._lock:
            self.usd += usd
            self.calls[model] = self.calls.get(model, 0) + 1

    def check(self):
        if self.usd >= self.cap:
            raise BudgetExceeded("cost cap of $%.2f reached" % self.cap)

    def summary(self):
        return {"usd": round(self.usd, 4), "calls": dict(self.calls)}


class BudgetExceeded(Exception):
    pass


def image_data_url(image_bytes, max_side=1024):
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _post(body):
    headers = {"Authorization": "Bearer " + config.MODEL_API_KEY, "Content-Type": "application/json"}
    last = None
    for attempt in range(4):
        try:
            r = requests.post(config.META_API, headers=headers, data=json.dumps(body), timeout=240)
            if r.status_code == 200:
                return r.json()
            last = "HTTP %s: %s" % (r.status_code, r.text[:200])
            if r.status_code in (400, 401, 403):
                break
        except requests.RequestException as e:
            last = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("Meta API call failed: %s" % last)


def respond(model, text, image_bytes=None, effort="low", web_search=False, budget=None, note=None, images=None):
    """One model call. Returns (output_text, sources), where sources are web_search results if any.
    image_bytes: one image; images: several, in order."""
    content = [{"type": "input_text", "text": text}]
    for im in ([image_bytes] if image_bytes is not None else []) + list(images or []):
        content.append({"type": "input_image", "image_url": image_data_url(im)})
    body = {"model": model, "stream": False, "reasoning": {"effort": effort},
            "input": [{"type": "message", "role": "user", "content": content}]}
    if web_search:
        body["tools"] = [{"type": "web_search"}]
        body["include"] = ["web_search_call.results"]
    if budget:
        budget.check()
    j = replay.cached("meta", body, lambda: _post(body), note=note)
    if budget:
        budget.add(model, j.get("usage", {}))
    return output_text(j), web_sources(j)


def output_text(j):
    parts = []
    for item in j.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
    return "".join(parts) or j.get("output_text", "")


def web_sources(j):
    out = []
    for item in j.get("output", []):
        if item.get("type") == "web_search_call":
            for r in item.get("results", []) or []:
                out.append({"title": r.get("title"), "url": r.get("url")})
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                for a in c.get("annotations", []) or []:
                    if a.get("type") == "url_citation":
                        out.append({"title": a.get("title"), "url": a.get("url"), "cited": True})
    return out


def parse_json(text):
    """First {...} object in a model answer."""
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < s:
        raise ValueError("no JSON object in model answer")
    return json.loads(text[s:e + 1])


def ask_json(model, text, retries=1, **kw):
    """Model call that must return a JSON object; one retry with a reminder if it does not."""
    for attempt in range(retries + 1):
        prompt = text if attempt == 0 else text + "\n\nReply with one valid JSON object only."
        answer, sources = respond(model, prompt, **kw)
        try:
            return parse_json(answer), sources
        except ValueError:
            continue
    raise ValueError("model did not return JSON")

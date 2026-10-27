"""Agent 2, the page reader (Muse Spark).

Opens a page where the photo was found and reports how that page describes the photo: which place, which date,
which event, and when the page itself was published. Only a short excerpt around the photo is kept (and recorded
for replay), not the whole page.
"""
import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import config, meta, replay

UA = {"User-Agent": "Mozilla/5.0 (compatible; Backstory/0.1; photo provenance research)"}
DATE_META = ("article:published_time", "og:published_time", "datePublished", "pubdate", "publishdate",
             "date", "dc.date", "dc.date.issued", "sailthru.date", "parsely-pub-date")


def _stem(url):
    name = urlparse(url).path.rsplit("/", 1)[-1]
    name = re.sub(r"\.(jpe?g|png|webp|gif|avif)$", "", name, flags=re.I)
    return re.sub(r"[-_](\d{2,4}x\d{2,4}|scaled|large|medium|small|thumb)$", "", name, flags=re.I)


def _published(soup):
    for m in soup.find_all("meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").lower()
        if key in (k.lower() for k in DATE_META) and m.get("content"):
            return m["content"][:25]
    for s in soup.find_all("script", type="application/ld+json"):
        found = re.search(r'"datePublished"\s*:\s*"([^"]+)"', s.string or "")
        if found:
            return found.group(1)[:25]
    t = soup.find("time", datetime=True)
    return t["datetime"][:25] if t else None


def _extract(url, image_urls):
    try:
        r = requests.get(url, headers=UA, timeout=20)
    except requests.RequestException as e:
        return {"ok": False, "error": type(e).__name__}
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return {"ok": False, "error": "HTTP %s" % r.status_code}
    soup = BeautifulSoup(r.content[:3_000_000], "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    published = _published(soup)
    stems = {_stem(u) for u in image_urls if len(_stem(u)) >= 6}
    near = []
    for img in soup.find_all("img"):
        src = " ".join(filter(None, [img.get("src"), img.get("data-src"), img.get("srcset")]))
        if stems and any(s in src for s in stems):
            fig = img.find_parent("figure")
            cap = fig.get_text(" ", strip=True) if fig else ""
            near.append(" | ".join(filter(None, [img.get("alt", ""), img.get("title", ""), cap]))[:400])
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return {"ok": True, "title": title[:200], "published": published, "photo_captions": near[:3],
            "excerpt": text[:2500]}


def fetch_page(url, image_urls):
    return replay.cached("page", {"url": url}, lambda: _extract(url, image_urls), note=url[:200],
                         keep=lambda r: r.get("ok") or r.get("error", "").startswith("HTTP 4"))


PROMPT = """A reverse image search found a photo on this web page. Report how this page describes that photo.

Page URL: {url}
Page title: {title}
Publication date from the page's metadata: {published}
Captions next to the matching image on the page: {captions}
Page text (start, may be cut):
{excerpt}

Reply with one JSON object:
{{"relevant": true if the page says anything about where/when/what the photo shows, else false,
  "place": "place the page gives for the photo, or null",
  "date": "date or period the page gives for the photo (YYYY-MM-DD, YYYY-MM or YYYY), or null",
  "event": "event the page says the photo shows, short, in English, or null",
  "page_date": "YYYY-MM-DD when the page was published, or null",
  "quote": "the shortest phrase from the page that supports place/date/event (max 25 words), or null"}}
Use only what is on the page. If the page does not say, use null."""


def read_page(url, image_urls, budget=None):
    page = fetch_page(url, image_urls)
    if not page.get("ok"):
        return {"url": url, "opened": False, "error": page.get("error")}
    prompt = PROMPT.format(url=url, title=page["title"], published=page["published"] or "not found",
                           captions=json.dumps(page["photo_captions"], ensure_ascii=False)
                           if page["photo_captions"] else "none found",
                           excerpt=page["excerpt"])
    try:
        data, _ = meta.ask_json(config.SPARK, prompt, budget=budget, note="read " + url[:150])
    except ValueError:
        data = {"relevant": False}
    data.update({"url": url, "opened": True, "title": page["title"]})
    return data

"""Fetch news items from every configured source."""
import hashlib
import html
import re
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from . import config

HEADERS = {"User-Agent": f"{config.BRAND_NAME.lower()}-news-bot/1.0"}
TIMEOUT = 20


def _clean(text):
    text = BeautifulSoup(html.unescape(text or ""), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def _uid(source_id, key):
    return source_id + ":" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _image_url(entry):
    """Largest image a feed entry offers, or ''."""
    candidates = []
    for m in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        if m.get("url") and m.get("medium", "image") == "image":
            candidates.append((int(m.get("width") or 0), m["url"]))
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/") and enc.get("href"):
            candidates.append((0, enc["href"]))
    if not candidates:
        return ""
    url = max(candidates)[1]
    # BBC thumbnails are 240px; the same image is served larger on this path.
    return re.sub(r"(ichef\.bbci\.co\.uk/ace/standard/)\d+/", r"\g<1>976/", url)


def _item(source, key, title, summary, link, published=None, image=""):
    return {
        "uid": _uid(source["id"], key),
        "source_id": source["id"],
        "source_name": source["name"],
        "title": _clean(title),
        "summary": _clean(summary)[:1500],
        "link": (link or "").strip(),
        "published": published,
        "image": image,
        "official": bool(source.get("official")),
        "media": bool(source.get("media")),
    }


def _fetch_rss(source):
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries:
        published = None
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        if stamp:
            published = datetime(*stamp[:6], tzinfo=timezone.utc).isoformat()
        key = e.get("id") or e.get("link") or e.get("title", "")
        items.append(_item(source, key, e.get("title", ""), e.get("summary", ""), e.get("link", ""),
                           published, _image_url(e)))
    return items


def _fetch_inoreader_html(source):
    """Parse Inoreader's free 'HTML clip' page: title link, then an article_content div."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for a in soup.select("a.title_link"):
        link = a.get("href", "")
        content = a.find_next("div", class_="article_content")
        summary = content.get_text(" ") if content else ""
        img = content.find("img") if content else None  # police appeals often include the photo
        image = img.get("src", "") if img and img.get("src", "").startswith("http") else ""
        items.append(_item(source, link, a.get_text(" "), summary, link, image=image))
    return items


def _fetch_ea_floods(source):
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    items = []
    for f in resp.json().get("items", []):
        level = f.get("severityLevel")
        if level not in (1, 2, 3):  # 4 = no longer in force
            continue
        area = f.get("description") or f.get("eaAreaName") or "South Yorkshire"
        severity = f.get("severity") or "Flood alert"
        changed = f.get("timeMessageChanged") or f.get("timeRaised") or ""
        key = f"{f.get('floodAreaID')}|{level}|{changed}"
        link = "https://check-for-flooding.service.gov.uk/target-area/" + str(f.get("floodAreaID", ""))
        items.append(_item(source, key, f"{severity}: {area}", f.get("message", ""), link, changed or None))
    return items


FETCHERS = {"rss": _fetch_rss, "inoreader_html": _fetch_inoreader_html, "ea_floods": _fetch_ea_floods}


def _keep(source, item):
    text = (item["title"] + " " + item["summary"]).lower()
    if source.get("media") and any(w in text for w in config.SKIP_WORDS):
        return False
    if source.get("local_only") and not any(p in text for p in config.LOCAL_PLACES):
        return False
    return bool(item["title"])


def fetch_all(log=print):
    """Return {source_id: [items]} - a source that fails is logged and skipped."""
    results = {}
    for source in config.SOURCES:
        try:
            items = FETCHERS[source["kind"]](source)
            results[source["id"]] = [i for i in items if _keep(source, i)]
            log(f"  {source['name']}: {len(items)} items, {len(results[source['id']])} kept")
        except Exception as exc:  # one broken feed must not stop the others
            log(f"  {source['name']}: FAILED ({exc})")
    return results


def source_by_id(source_id):
    for s in config.SOURCES:
        if s["id"] == source_id:
            return s
    return {"id": source_id, "name": source_id, "emoji": "💬" if source_id == "ig_dms" else "📝"}

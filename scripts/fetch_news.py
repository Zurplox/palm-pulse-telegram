#!/usr/bin/env python3
"""Ambil berita sawit via RSS langsung (infosawit.com dll) + Google News RSS
(TANPA API key) -> data/news.json. Mendukung format RSS (item) & Atom (entry).
Hanya pustaka standar Python.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "news.json")
UA = {"User-Agent": "Mozilla/5.0 (brief-pagi bot)"}


def load_cfg():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def gnews_url(query):
    # hl=id -> hasil Bahasa Indonesia
    q = urllib.parse.quote(query)
    return "https://news.google.com/rss/search?q=%s&hl=id&gl=ID&ceid=ID:id" % q


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(el, names):
    for c in el:
        if _local(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return ""


def _parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)  # RFC822 (RSS)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))  # ISO (Atom)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_feed(xml_bytes, fallback_source=""):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _child_text(el, ("title",))
        link = ""
        for c in el:
            if _local(c.tag) == "link":
                href = c.get("href")
                link = href if href else (c.text or "").strip()
                if href and c.get("rel", "alternate") == "alternate":
                    break
        pub = _child_text(el, ("pubDate", "published", "updated", "date"))
        source = _child_text(el, ("source",)) or fallback_source
        when = _parse_date(pub)
        if title:
            items.append({"title": title, "link": link, "source": source,
                          "published": when.isoformat() if when else None,
                          "_dt": when})
    return items


def norm(title):
    t = title.lower()
    t = re.sub(r"\s+-\s+[^-]+$", "", t)      # buang " - Sumber" di akhir
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def main():
    cfg = load_cfg().get("news", {})
    lookback = cfg.get("lookback_hours", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback)
    # (url, fallback_source)
    sources = [(u, domain(u)) for u in cfg.get("extra_feeds", [])]
    sources += [(gnews_url(q), "") for q in cfg.get("queries", [])]
    seen, out = set(), []
    for url, fb in sources:
        try:
            items = parse_feed(fetch(url), fb)
        except Exception as e:
            print("skip feed (%s): %s" % (fb or url[:40], str(e)[:70]))
            continue
        for it in items:
            if it["_dt"] and it["_dt"] < cutoff:
                continue
            key = norm(it["title"])
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(it)
    out.sort(key=lambda x: x["_dt"] or datetime.min.replace(tzinfo=timezone.utc),
             reverse=True)
    out = out[: cfg.get("max_items", 10)]
    for it in out:
        it.pop("_dt", None)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK: %d berita -> data/news.json" % len(out))


if __name__ == "__main__":
    main()

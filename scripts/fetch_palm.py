#!/usr/bin/env python3
"""Ambil feed Palm Pulse yang sudah dipublikasikan -> data/palm.json.

HANYA BACA. Satu HTTP GET ke GitHub Pages milik palm-pulse. Repo ini tidak
punya token tulis ke sana dan tidak boleh mengubah apa pun di repo itu:
website, workflow harian, dan aplikasi Android harus tetap apa adanya.

Tidak pernah gagal keras: kalau feed mati, brief tetap terbit tanpa blok TBS.
Hanya pustaka standar Python.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "palm.json")
DEFAULT_FEED = "https://zurplox.github.io/palm-pulse/data/latest.json"
UA = "brief-pagi/1.0 (+read-only palm pulse feed)"


def setting(name, default=""):
    return (os.environ.get(name) or "").strip() or default


def load_cfg():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def feed_url(cfg):
    palm = cfg.get("palm") or {}
    return setting("PALM_FEED_URL", palm.get("feed_url") or DEFAULT_FEED)


def fetch(url):
    # Cache-buster: GitHub Pages kadang menyajikan salinan lama.
    sep = "&" if "?" in url else "?"
    target = "%s%st=%d" % (url, sep, int(datetime.now(timezone.utc).timestamp()))
    req = urllib.request.Request(target, headers={
        "User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    cfg = load_cfg()
    palm = cfg.get("palm") or {}
    if palm.get("enabled") is False:
        print("Palm Pulse dimatikan di config.json, dilewati.")
        return
    url = feed_url(cfg)
    try:
        data = fetch(url)
    except Exception as e:
        # Pertahankan data/palm.json lama kalau ada: lebih baik harga kemarin
        # (dengan catatan umur) daripada tidak ada blok harga sama sekali.
        print("Feed Palm Pulse tidak terbaca (%s). Pakai salinan terakhir."
              % type(e).__name__)
        return
    if not isinstance(data, dict):
        print("Feed Palm Pulse bukan objek JSON, dilewati.")
        return
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("Gagal menyimpan palm.json:", e)
        return
    prices = [p for p in (data.get("tbs_prices") or []) if isinstance(p, dict)]
    print("OK -> data/palm.json (edisi %s, %d harga TBS)"
          % (data.get("generated_at"), len(prices)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fetch_palm dilewati tanpa merusak workflow:", type(e).__name__)

#!/usr/bin/env python3
"""Ambil feed kebun-sawit-cuaca yang sudah dipublikasikan.

  data/cuaca.json       -> hujan, suhu, angin, prakiraan
  data/lingkungan.json  -> banjir, karhutla, kualitas udara

HANYA BACA. Dua HTTP GET biasa ke GitHub Pages milik repo itu, sama seperti
membukanya di browser. Repo ini tidak punya token tulis ke sana dan tidak boleh
mengubah apa pun di repo cuaca: workflow, dashboard, maupun bentuk JSON-nya.

Tidak pernah gagal keras: kalau salah satu feed mati, salinan terakhir tetap
dipakai dan brief tetap terbit tanpa blok itu.
Hanya pustaka standar Python.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "https://zurplox.github.io/kebun-sawit-cuaca/"
UA = "brief-pagi/1.0 (+read-only cuaca feed)"
# nama lokal -> path di repo cuaca
FILES = (("cuaca.json", "data/cuaca.json"),
         ("lingkungan.json", "data/lingkungan.json"))


def setting(name, default=""):
    return (os.environ.get(name) or "").strip() or default


def load_cfg():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def base_url(cfg):
    settings = cfg.get("cuaca") or {}
    url = setting("CUACA_BASE_URL", settings.get("base_url") or DEFAULT_BASE)
    return url if url.endswith("/") else url + "/"


def fetch(url):
    # Cache-buster: GitHub Pages kadang menyajikan salinan lama.
    sep = "&" if "?" in url else "?"
    target = "%s%st=%d" % (url, sep, int(datetime.now(timezone.utc).timestamp()))
    req = urllib.request.Request(target, headers={
        "User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def save(name, data):
    out = os.path.join(ROOT, "data", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def main():
    cfg = load_cfg()
    settings = cfg.get("cuaca") or {}
    if settings.get("enabled") is False:
        print("Feed cuaca dimatikan di config.json, dilewati.")
        return
    base = base_url(cfg)
    for name, path in FILES:
        url = base + path
        try:
            data = fetch(url)
        except Exception as e:
            # Salinan lama lebih berguna daripada tidak ada blok sama sekali.
            print("Feed %s tidak terbaca (%s). Pakai salinan terakhir."
                  % (name, type(e).__name__))
            continue
        if not isinstance(data, dict):
            print("Feed %s bukan objek JSON, dilewati." % name)
            continue
        try:
            save(name, data)
        except OSError as e:
            print("Gagal menyimpan %s: %s" % (name, e))
            continue
        print("OK -> data/%s (diperbarui %s)" % (name, data.get("updated_at")))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fetch_cuaca dilewati tanpa merusak workflow:", type(e).__name__)

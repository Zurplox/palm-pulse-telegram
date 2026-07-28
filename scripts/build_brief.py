#!/usr/bin/env python3
"""Susun brief pagi dari data/palm.json + data/news.json + data/markets.json.

Satu pesan gabungan: harga TBS & ringkasan Palm Pulse, kutipan pasar, lalu
berita sawit & agri.

Kalau ada secret GEMINI_API_KEY -> ringkas pakai AI (Gemini free tier).
Kalau tidak -> digest rapi tanpa AI (tetap jalan, gratis).
Output: data/brief.json + data/brief_message.txt
Hanya pustaka standar Python.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def load(p, d=None):
    p = os.path.join(ROOT, p)
    if not os.path.exists(p):
        return d
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return d


def today_str(cfg):
    off = timezone(timedelta(hours=cfg.get("utc_offset_hours", 8)))
    d = datetime.now(off).date()
    return "%02d %s %d" % (d.day, BULAN[d.month], d.year)


def fmt_num(n):
    """Data pasar dianggap tidak tepercaya: angka berbentuk string atau rusak
    tidak boleh menjatuhkan seluruh brief."""
    n = palm.as_number(n)
    if n is None:
        return "-"
    if abs(n) >= 1000:
        return format(int(round(n)), ",d").replace(",", ".")
    return ("%.4f" % n).rstrip("0").rstrip(".") if abs(n) < 10 else ("%.2f" % n)


def fmt_pct(raw, pct):
    """Tampilan persen dipertahankan persis seperti sebelumnya (-2.0 tetap
    "-2.0", bukan "-2"), tapi nilai non-angka tidak lagi bikin crash."""
    if pct is None:
        return "?"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return str(raw)
    text = ("%.2f" % pct).rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def markets_block(markets):
    if not isinstance(markets, dict):
        return "  (data pasar tidak tersedia)"
    lines = []
    for t in markets.get("tickers") or []:
        if not isinstance(t, dict):
            continue
        raw = t.get("pct")
        pct = palm.as_number(raw)
        arrow = "\u2192"
        if pct is not None:
            arrow = "\u25b2" if pct > 0 else ("\u25bc" if pct < 0 else "\u2192")
        label = str(t.get("label") or t.get("yahoo") or "?")
        lines.append("  %s %s: %s (%s%s%%)" % (
            arrow, label, fmt_num(t.get("last")),
            "+" if (pct or 0) > 0 else "", fmt_pct(raw, pct)))
    for f in markets.get("fx") or []:
        if not isinstance(f, dict) or not f.get("pair"):
            continue
        lines.append("  \U0001F4B1 %s: %s" % (f["pair"], fmt_num(f.get("rate"))))
    return "\n".join(lines) if lines else "  (data pasar tidak tersedia)"


def news_block(news):
    lines = []
    for n in news if isinstance(news, list) else []:
        if not isinstance(n, dict):
            continue
        title = str(n.get("title") or "").strip()
        if not title:
            continue
        src = (" \u2014 " + str(n["source"])) if n.get("source") else ""
        lines.append("\u2022 %s%s" % (title, src))
    return "\n".join(lines) if lines else "(tidak ada berita baru)"


def gemini_summary(payload_text, api_key):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-1.5-flash:generateContent?key=" + api_key)
    prompt = (
        "Kamu editor brief pagi untuk pemilik kebun sawit di Riau yang juga "
        "investor. Dari data harga TBS, berita & pasar di bawah, tulis "
        "ringkasan SINGKAT dalam Bahasa Indonesia: 3-5 poin peluru paling "
        "penting untuk bisnis sawit & keputusan hari ini, lalu 1 baris "
        "sentimen pasar. Padat, tanpa basa-basi, maksimal ~120 kata. Jangan "
        "mengarang; hanya dari data.\n\n" + payload_text)
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def build_message(cfg, palm_data, markets, news, ai_summary=None, now=None):
    title = "%s *%s* \u2014 %s" % (cfg.get("emoji", "\U0001F4F0"),
                                   cfg.get("brief_title", "BRIEF PAGI"),
                                   today_str(cfg))
    parts = [title, ""]
    if ai_summary:
        parts += ["\U0001F9E0 *Ringkasan:*", ai_summary, ""]

    # Palm Pulse duluan: harga TBS adalah angka yang paling dipakai pagi hari.
    block = palm.palm_block(palm_data, cfg, now)
    if block:
        parts += [block, ""]

    parts += ["\U0001F4C8 *Pasar:*", markets_block(markets), "",
              "\U0001F4F0 *Berita sawit & agri:*", news_block(news)]

    site = (cfg.get("palm") or {}).get("site_url")
    if site:
        parts += ["", "Palm Pulse selengkapnya: %s" % site]
    return "\n".join(p for p in parts if p is not None)


def main():
    cfg = load("config.json", {}) or {}
    news = load("data/news.json", []) or []
    markets = load("data/markets.json", {}) or {}
    palm_data = load("data/palm.json", {}) or {}

    block = palm.palm_block(palm_data, cfg)
    payload = "HARGA TBS & PALM PULSE:\n%s\n\nPASAR:\n%s\n\nBERITA:\n%s" % (
        block or "(tidak ada data)",
        markets_block(markets),
        news_block(news))

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    ai_summary = None
    if api_key and (news or palm_data):
        try:
            ai_summary = gemini_summary(payload, api_key)
        except Exception as e:
            print("Gemini gagal, pakai digest biasa:", str(e)[:100])

    message = build_message(cfg, palm_data, markets, news, ai_summary)
    title = message.split("\n", 1)[0]

    with open(os.path.join(ROOT, "data", "brief.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title, "ai_summary": ai_summary, "news": news,
                   "markets": markets,
                   "palm": {
                       "edition": palm.edition_date(palm_data.get("generated_at")),
                       "generated_at": palm_data.get("generated_at"),
                       "tbs_prices": palm_data.get("tbs_prices") or [],
                       "bullets": palm.bullets(
                           palm_data,
                           (cfg.get("palm") or {}).get("max_bullets", 4)),
                   },
                   "generated": datetime.now(timezone.utc)
                   .isoformat(timespec="minutes")}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "data", "brief_message.txt"), "w",
              encoding="utf-8") as f:
        f.write(message)
    print("OK -> data/brief.json + data/brief_message.txt")
    print("AI:", "ya" if ai_summary else "tidak (digest biasa)")
    print("Palm Pulse:", "ya" if block else "tidak")
    print("Panjang pesan:", len(message), "karakter")
    print("\n" + message)


if __name__ == "__main__":
    main()

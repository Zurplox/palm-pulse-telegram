#!/usr/bin/env python3
"""Susun brief pagi jadi satu pesan.

Sumber data (sudah diambil lebih dulu oleh script fetch_*):
  data/palm.json        <- Palm Pulse: harga TBS, ringkasan, berita sawit
  data/cuaca.json       <- kebun-sawit-cuaca: hujan, suhu, angin, prakiraan
  data/lingkungan.json  <- kebun-sawit-cuaca: banjir, karhutla, udara
  data/markets.json     <- internet: Yahoo Finance + kurs

Urutan pesan: harga TBS -> cuaca -> banjir/karhutla/udara -> pasar -> berita.

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
import cuaca as cuaca_fmt  # noqa: E402
import palm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def as_dict(value):
    """Feed milik repo lain: bentuknya bisa berubah kapan saja. Kalau sebuah
    berkas ternyata bukan objek JSON (mis. list atau string), perlakukan
    sebagai kosong daripada membuat build_brief.py mati dan workflow merah."""
    return value if isinstance(value, dict) else {}


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


def gemini_summary(payload_text, api_key):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-1.5-flash:generateContent?key=" + api_key)
    prompt = (
        "Kamu editor brief pagi untuk pemilik kebun sawit di Riau yang juga "
        "investor. Dari data harga TBS, cuaca kebun, kondisi banjir/karhutla, "
        "pasar, dan berita di bawah, tulis ringkasan SINGKAT dalam Bahasa "
        "Indonesia: 3-5 poin peluru paling penting untuk keputusan kebun hari "
        "ini (panen, pemupukan, angkut), lalu 1 baris sentimen pasar. Padat, "
        "tanpa basa-basi, maksimal ~120 kata. Jangan mengarang; hanya dari "
        "data.\n\n" + payload_text)
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def build_message(cfg, palm_data, cuaca_data, ling_data, markets,
                  ai_summary=None, now=None):
    """Rakit pesan lengkap. Setiap seksi yang tidak punya data yang bisa
    dipakai akan hilang sendiri, bukan tampil sebagai placeholder kosong."""
    cfg = cfg or {}
    title = "%s *%s* \u2014 %s" % (cfg.get("emoji", "\U0001F4F0"),
                                   cfg.get("brief_title", "BRIEF PAGI"),
                                   today_str(cfg))
    parts = [title, ""]
    if ai_summary:
        parts += ["\U0001F9E0 *Ringkasan:*", ai_summary, ""]

    # Harga TBS duluan: angka yang paling dipakai pagi hari.
    block = palm.palm_block(palm_data, cfg, now)
    if block:
        parts += [block, ""]

    weather = cuaca_fmt.weather_block(cuaca_data, cfg, now)
    if weather:
        parts += [weather, ""]

    env = cuaca_fmt.env_block(ling_data, cfg)
    if env:
        parts += [env, ""]

    parts += ["\U0001F4C8 *Pasar:*", markets_block(markets)]

    max_stories = (cfg.get("palm") or {}).get("max_stories", 8)
    news = palm.stories_block(palm_data, max_stories)
    if news:
        parts += ["", "\U0001F4F0 *Berita sawit (Palm Pulse):*", news]

    footer = []
    site = (cfg.get("palm") or {}).get("site_url")
    if site:
        footer.append("Palm Pulse: %s" % site)
    weather_site = (cfg.get("cuaca") or {}).get("site_url")
    if weather_site:
        footer.append("Cuaca kebun: %s" % weather_site)
    if footer:
        parts += [""] + footer
    return "\n".join(p for p in parts if p is not None)


def main():
    cfg = as_dict(load("config.json", {}))
    markets = as_dict(load("data/markets.json", {}))
    palm_data = as_dict(load("data/palm.json", {}))
    cuaca_data = as_dict(load("data/cuaca.json", {}))
    ling_data = as_dict(load("data/lingkungan.json", {}))

    max_stories = (cfg.get("palm") or {}).get("max_stories", 8)
    block = palm.palm_block(palm_data, cfg)
    weather = cuaca_fmt.weather_block(cuaca_data, cfg)
    env = cuaca_fmt.env_block(ling_data, cfg)
    news = palm.stories(palm_data, max_stories)

    payload = ("HARGA TBS & RINGKASAN SAWIT:\n%s\n\nCUACA KEBUN:\n%s\n\n"
               "BANJIR/KARHUTLA/UDARA:\n%s\n\nPASAR:\n%s\n\nBERITA SAWIT:\n%s"
               % (block or "(tidak ada data)",
                  weather or "(tidak ada data)",
                  env or "(tidak ada data)",
                  markets_block(markets),
                  palm.stories_block(palm_data, max_stories) or
                  "(tidak ada berita)"))

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    ai_summary = None
    if api_key and (palm_data or cuaca_data or markets):
        try:
            ai_summary = gemini_summary(payload, api_key)
        except Exception as e:
            print("Gemini gagal, pakai digest biasa:", str(e)[:100])

    message = build_message(cfg, palm_data, cuaca_data, ling_data, markets,
                            ai_summary)
    title = message.split("\n", 1)[0]

    today = cuaca_data.get("today") if isinstance(
        cuaca_data.get("today"), dict) else {}
    with open(os.path.join(ROOT, "data", "brief.json"), "w",
              encoding="utf-8") as f:
        json.dump({"title": title,
                   "ai_summary": ai_summary,
                   # index.html memakai kunci 'link'
                   "news": [{"title": n["title"], "source": n["source"],
                             "link": n["url"]} for n in news],
                   "markets": markets,
                   "palm": {
                       "edition": palm.edition_date(
                           palm_data.get("generated_at")),
                       "generated_at": palm_data.get("generated_at"),
                       "tbs_prices": palm_data.get("tbs_prices") or [],
                       "bullets": palm.bullets(
                           palm_data,
                           (cfg.get("palm") or {}).get("max_bullets", 4)),
                   },
                   "cuaca": {
                       "updated_at": cuaca_data.get("updated_at"),
                       "farm_name": cuaca_data.get("farm_name"),
                       "today": today,
                   },
                   "lingkungan": {
                       "updated_at": ling_data.get("updated_at"),
                       "flood": ling_data.get("flood") or {},
                       "fire": ling_data.get("fire") or {},
                       "air": ling_data.get("air") or {},
                   },
                   "generated": datetime.now(timezone.utc)
                   .isoformat(timespec="minutes")},
                  f, ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "data", "brief_message.txt"), "w",
              encoding="utf-8") as f:
        f.write(message)
    print("OK -> data/brief.json + data/brief_message.txt")
    print("AI:", "ya" if ai_summary else "tidak (digest biasa)")
    print("Palm Pulse:", "ya" if block else "tidak")
    print("Cuaca:", "ya" if weather else "tidak")
    print("Lingkungan:", "ya" if env else "tidak")
    print("Berita sawit:", len(news))
    print("Panjang pesan:", len(message), "karakter")
    print("\n" + message)


if __name__ == "__main__":
    main()

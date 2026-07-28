#!/usr/bin/env python3
"""Kutipan pasar via Yahoo Finance (TANPA key) untuk ETF/saham & kurs (FX).
Kalau Yahoo gagal untuk FX, fallback ke exchangerate.host.
-> data/markets.json. Hanya pustaka standar Python.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "markets.json")
UA = {"User-Agent": "Mozilla/5.0 (brief-pagi bot)"}


def load_cfg():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def yahoo_quote(symbol):
    """Harga terakhir + % perubahan dari Yahoo Finance chart API."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?interval=1d&range=5d" % urllib.parse.quote(symbol))
    data = fetch_json(url)
    res = ((data.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res.get("meta", {})
    last = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if last is None:
        return None
    pct = round((last - prev) / prev * 100, 2) if prev else None
    return {"last": round(float(last), 4), "pct": pct}


def fx_fallback(base, quote):
    url = "https://api.exchangerate.host/latest?base=%s&symbols=%s" % (base, quote)
    data = fetch_json(url)
    return (data.get("rates") or {}).get(quote)


def main():
    cfg = load_cfg().get("markets", {})
    tickers = []
    for t in cfg.get("tickers", []):
        sym = t.get("yahoo") or t.get("symbol")
        try:
            q = yahoo_quote(sym)
        except Exception as e:
            print("ticker skip %s: %s" % (sym, str(e)[:60]))
            q = None
        if q:
            tickers.append({"label": t.get("label", sym), **q})

    fx = []
    for p in cfg.get("fx", []):
        base, quote = p["base"], p["quote"]
        sym = "%s%s=X" % (base, quote)  # simbol FX Yahoo, mis. USDIDR=X
        rate = None
        try:
            q = yahoo_quote(sym)
            rate = q["last"] if q else None
        except Exception as e:
            print("fx yahoo skip %s: %s" % (sym, str(e)[:60]))
        if rate is None:
            try:
                rate = fx_fallback(base, quote)
            except Exception as e:
                print("fx fallback skip %s/%s: %s" % (base, quote, str(e)[:60]))
        if rate is not None:
            fx.append({"pair": "%s/%s" % (base, quote), "rate": round(float(rate), 4)})

    result = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
              "tickers": tickers, "fx": fx}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("OK: %d ticker, %d kurs -> data/markets.json" % (len(tickers), len(fx)))


if __name__ == "__main__":
    main()

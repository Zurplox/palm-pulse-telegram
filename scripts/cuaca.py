#!/usr/bin/env python3
"""Format bagian cuaca & lingkungan dari feed repo kebun-sawit-cuaca.

Sumber: data/cuaca.json (hujan, suhu, angin, prakiraan) dan
data/lingkungan.json (banjir, karhutla, kualitas udara) yang sudah
dipublikasikan repo itu ke GitHub Pages.

Semua field dianggap TIDAK tepercaya: hilang, null, salah tipe, atau tidak bisa
di-parse ditangani tanpa raise. Kata "None" tidak pernah dicetak. Kalau tidak
ada isi yang berguna, blok dikembalikan sebagai "" supaya seksinya hilang, bukan
menampilkan placeholder kosong.

Hanya pustaka standar Python.
"""
from datetime import datetime, timezone


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def trim(value):
    """Angka rapi: 0.4 -> "0.4", 25.0 -> "25"."""
    n = num(value)
    if n is None:
        return None
    return ("%.1f" % n).rstrip("0").rstrip(".")


def parse_stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def hours_old(value, now=None):
    stamp = parse_stamp(value)
    if stamp is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - stamp).total_seconds() / 3600


def today_line(today):
    """Baris utama hari ini: kondisi, hujan, peluang, rentang suhu."""
    if not isinstance(today, dict):
        return ""
    bits = []
    condition = str(today.get("condition") or "").strip()
    if condition:
        bits.append(condition)
    precip = trim(today.get("precip"))
    prob = num(today.get("prob"))
    if precip is not None:
        rain = "hujan %s mm" % precip
        if prob is not None:
            rain += " (peluang %d%%)" % int(round(prob))
        bits.append(rain)
    elif prob is not None:
        bits.append("peluang hujan %d%%" % int(round(prob)))
    tmin, tmax = trim(today.get("tmin")), trim(today.get("tmax"))
    if tmin is not None and tmax is not None:
        bits.append("%s\u2013%s\u00b0C" % (tmin, tmax))
    return "  " + ", ".join(bits) if bits else ""


def wind_line(today):
    if not isinstance(today, dict):
        return ""
    speed = trim(today.get("wind"))
    if speed is None:
        return ""
    direction = str(today.get("wind_dir") or "").strip()
    text = "  Angin %s km/jam" % speed
    if direction:
        text = "  Angin %s %s km/jam" % (direction, speed)
    gust = trim(today.get("gust"))
    if gust is not None:
        text += " (hembusan %s)" % gust
    return text


def forecast_lines(days, limit=3, today_date=None):
    """Ambil prakiraan hari berikutnya. Baris 'actual' (data historis) dilewati
    supaya yang tampil hanya hari depan."""
    if not isinstance(days, list):
        return []
    out = []
    for day in days:
        if not isinstance(day, dict):
            continue
        if str(day.get("kind") or "").strip() == "actual":
            continue
        date = str(day.get("date") or "").strip()
        if not date or (today_date and date <= str(today_date)):
            continue
        precip = trim(day.get("precip"))
        prob = num(day.get("prob"))
        bits = []
        if precip is not None:
            bits.append("%s mm" % precip)
        if prob is not None:
            bits.append("%d%%" % int(round(prob)))
        if not bits:
            continue
        out.append("  %s: %s" % (date, ", ".join(bits)))
        if len(out) >= limit:
            break
    return out


def flood_line(flood):
    if not isinstance(flood, dict):
        return ""
    status = str(flood.get("status") or "").strip()
    discharge = trim(flood.get("river_discharge"))
    trend = str(flood.get("trend") or "").strip()
    if not status and discharge is None:
        return ""
    detail = []
    if discharge is not None:
        unit = str(flood.get("unit") or "m3/s").strip()
        detail.append("debit %s %s" % (discharge, unit))
    if trend:
        detail.append(trend)
    text = "  Banjir: %s" % (status or "-")
    if detail:
        text += " (%s)" % ", ".join(detail)
    return text


def fire_line(fire):
    if not isinstance(fire, dict):
        return ""
    status = str(fire.get("status") or "").strip()
    nearest = fire.get("nearest")
    detail = ""
    if isinstance(nearest, dict):
        km = trim(nearest.get("km"))
        if km is not None:
            direction = str(nearest.get("dir") or "").strip()
            place = str(nearest.get("place") or "").strip()
            detail = " \u2014 titik terdekat %s km" % km
            if direction:
                detail += " %s" % direction
            if place:
                detail += " (%s)" % place
    if not status and not detail:
        return ""
    return "  Karhutla: %s%s" % (status or "-", detail)


def air_line(air):
    if not isinstance(air, dict):
        return ""
    aqi = num(air.get("us_aqi"))
    category = str(air.get("category") or "").strip()
    haze = str(air.get("haze") or "").strip()
    if aqi is None and not category and not haze:
        return ""
    bits = []
    if aqi is not None:
        bits.append("AQI %d" % int(round(aqi)))
    if category:
        bits.append(category)
    if haze:
        bits.append(haze)
    return "  Udara: %s" % ", ".join(bits)


def weather_block(cuaca, cfg=None, now=None):
    """Blok cuaca kebun. "" kalau tidak ada isi yang berguna."""
    cfg = cfg or {}
    if not isinstance(cuaca, dict):
        return ""
    settings = cfg.get("cuaca") or {}
    limit = settings.get("forecast_days", 3)
    stale_hours = settings.get("stale_hours", 24)

    today = cuaca.get("today") if isinstance(cuaca.get("today"), dict) else {}
    lines = []
    main = today_line(today)
    if main:
        lines.append(main)
    wind = wind_line(today)
    if wind:
        lines.append(wind)

    ahead = forecast_lines(cuaca.get("days"), limit, today.get("date"))
    if ahead:
        lines.append("  Prakiraan:")
        lines += ahead

    if not lines:
        return ""

    emoji = str(today.get("emoji") or "\U0001F326").strip() or "\U0001F326"
    farm = str(cuaca.get("farm_name") or "").strip()
    heading = "%s *Cuaca kebun%s*" % (emoji, (" \u2014 " + farm) if farm else "")

    age = hours_old(cuaca.get("updated_at"), now)
    if age is not None and age > stale_hours:
        lines.append("  (data cuaca berumur %.0f jam, feed belum diperbarui)"
                     % age)
    return "\n".join([heading] + lines)


def env_block(lingkungan, cfg=None):
    """Blok banjir / karhutla / udara. "" kalau tidak ada isi yang berguna."""
    if not isinstance(lingkungan, dict):
        return ""
    lines = [ln for ln in (flood_line(lingkungan.get("flood")),
                           fire_line(lingkungan.get("fire")),
                           air_line(lingkungan.get("air"))) if ln]
    if not lines:
        return ""
    return "\n".join(["\U0001F30A *Banjir, karhutla & udara:*"] + lines)

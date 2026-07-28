#!/usr/bin/env python3
"""Format bagian Palm Pulse (harga TBS + ringkasan) untuk brief pagi.

Logika di sini diangkat dari repo palm-pulse-telegram supaya perilakunya sama
persis: urutan umur tanaman yang dipakai widget Android, separator ribuan
Indonesia, dan penanganan data rusak yang tidak boleh menjatuhkan brief.

Semua field feed dianggap TIDAK tepercaya: hilang, null, salah tipe dan tidak
bisa di-parse semuanya ditangani tanpa raise. Kata "None" tidak pernah dicetak.

Hanya pustaka standar Python.
"""
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]
# Preferensi umur tanaman yang sama dengan widget Android Palm Pulse.
AGE_ORDER = ("5", "6", "4", "9")


def parse_stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def edition_date(value):
    """Tanggal edisi dalam WIB: edisi 22:30 UTC harus tampil sebagai hari
    berikutnya, bukan hari UTC-nya."""
    stamp = parse_stamp(value)
    if stamp is None:
        return None
    local = stamp.astimezone(WIB)
    return "%d %s %d" % (local.day, BULAN[local.month - 1], local.year)


def hours_old(value, now=None):
    stamp = parse_stamp(value)
    if stamp is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - stamp).total_seconds() / 3600


def as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rupiah(value):
    number = as_number(value)
    if number is None:
        return "-"
    return "Rp" + format(number, ",.0f").replace(",", ".")


def price_value(price):
    ages = price.get("age_prices_rp_per_kg") or {}
    if isinstance(ages, dict):
        for key in AGE_ORDER:
            if as_number(ages.get(key)) is not None:
                return ages.get(key)
    return price.get("price_rp_per_kg")


def price_line(price):
    """Kembalikan "" kalau tidak ada angka yang bisa dipakai, supaya brief tidak
    pernah menampilkan placeholder seperti "Plasma: -/kg". Nilai perubahan yang
    rusak cukup menghilangkan panah arah, bukan menjatuhkan seluruh brief."""
    if not isinstance(price, dict):
        return ""
    value = as_number(price_value(price))
    if value is None:
        return ""
    change = as_number(price.get("change_rp_per_kg"))
    detail = ""
    if change:
        detail = " (%s %s)" % ("naik" if change > 0 else "turun",
                               rupiah(abs(change)))
    scheme = str(price.get("scheme") or "TBS").strip() or "TBS"
    return "  %s: %s/kg%s" % (scheme, rupiah(value), detail)


def price_heading(prices):
    head = prices[0]
    region = str(head.get("region") or "").strip().upper()
    heading = " ".join(p for p in ("Harga TBS", region.title()) if p)
    if head.get("valid_from") and head.get("valid_to"):
        heading += " (%s s/d %s)" % (head["valid_from"], head["valid_to"])
    return heading


def bullets(data, limit=4):
    summary = str(data.get("master_summary") or "")
    out = []
    for line in summary.splitlines():
        line = line.strip()
        if line.startswith("-") or line.startswith("\u2022"):
            cleaned = line.lstrip("-").lstrip("\u2022").strip()
            if cleaned:
                out.append(cleaned)
    return out[:limit]


def palm_block(data, cfg=None, now=None):
    """Bangun blok Palm Pulse. Kembalikan "" kalau tidak ada isi yang berguna.

    Berita Palm Pulse sengaja TIDAK dimasukkan: repo ini sudah punya seksi
    'Berita sawit & agri' sendiri dari RSS, jadi menambahkannya hanya membuat
    pesan dobel dan panjang.
    """
    cfg = cfg or {}
    if not isinstance(data, dict):
        return ""
    palm_cfg = cfg.get("palm") or {}
    stale_hours = palm_cfg.get("stale_hours", 36)
    max_bullets = palm_cfg.get("max_bullets", 4)

    lines = []
    prices = [p for p in (data.get("tbs_prices") or []) if isinstance(p, dict)]
    price_lines = [ln for ln in (price_line(p) for p in prices[:3]) if ln]
    if price_lines:
        lines.append("\U0001F334 *%s*" % price_heading(prices))
        lines += price_lines

    points = bullets(data, max_bullets)
    if points:
        if lines:
            lines.append("")
        lines.append("\U0001F9ED *Ringkasan Palm Pulse:*")
        lines += ["\u2022 %s" % p for p in points]

    if not lines:
        return ""

    age = hours_old(data.get("generated_at"), now)
    if age is not None and age > stale_hours:
        lines.append("  (edisi Palm Pulse berumur %.0f jam, feed belum "
                     "diperbarui)" % age)
    return "\n".join(lines)

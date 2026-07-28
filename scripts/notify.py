#!/usr/bin/env python3
"""Kirim data/brief_message.txt ke WhatsApp (CallMeBot) dan/atau Telegram.

Judul pesan sudah jelas & beda dari repo lain (lihat config.brief_title).

Secret / env:
  WA_PHONE, WA_APIKEY                 -> WhatsApp (CallMeBot)
  TG_TOKEN, TG_CHAT_ID                -> Telegram
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID-> alias Telegram (nama ala palm-pulse)
  FORCE_SEND=1                        -> paksa kirim walau sudah kirim hari ini

Aturan penting:
- Kirim maks 1x/hari PER KANAL (data/last_sent.json). Kalau WhatsApp berhasil
  tapi Telegram gagal, besok/percobaan berikutnya Telegram tetap dicoba lagi.
- Telegram dikirim TANPA parse_mode (plain text). Judul berita sering memuat
  '*', '_', '[', '(' yang bikin Markdown/HTML ditolak Telegram.
- Pesan dipecah otomatis di bawah batas 4096 karakter Telegram.
- Token tidak pernah dicetak: pesan error dibersihkan sebelum di-log.
- Script selalu exit 0 supaya workflow tidak merah gara-gara notifikasi.

Hanya pustaka standar Python.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST = os.path.join(ROOT, "data", "last_sent.json")

# CallMeBot: batas panjang URL-encoded per permintaan.
ENC_LIMIT = 1300
# Telegram menolak > 4096 karakter; sisakan ruang untuk penanda bagian.
TG_LIMIT = 3800
# Jeda sebelum satu kali percobaan ulang saat 429 / 5xx.
RETRY_PAUSE = 5


def setting(name, default=""):
    """Variabel GitHub yang tidak diisi datang sebagai string kosong, bukan
    absen. os.getenv(name, default) polos akan mengembalikan "" dan merusak
    konfigurasi, jadi selalu jatuh ke default kalau nilainya kosong."""
    return (os.environ.get(name) or "").strip() or default


def load(p, d=None):
    if not os.path.exists(p):
        return d
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return d


def scrub(text):
    """Buang apa pun yang mirip token bot dari teks error sebelum dicetak.
    Telegram menaruh token di URL, dan urllib suka menyertakan URL di pesan
    error."""
    text = str(text)
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<TOKEN>", text)
    text = re.sub(r"\d{6,}:[A-Za-z0-9_-]{20,}", "<TOKEN>", text)
    return text


def plain(text):
    """Ubah penekanan gaya WhatsApp (*tebal*) jadi teks polos untuk Telegram.
    Tanpa parse_mode, tanda bintang hanya jadi sampah visual."""
    return re.sub(r"\*(.+?)\*", r"\1", text)


def split_chunks(text, limit, measure=len):
    """Pecah di batas baris supaya URL tidak pernah terpotong separuh."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        cand = (cur + "\n" + line) if cur else line
        if measure(cand) > limit and cur:
            chunks.append(cur)
            cur = line
        else:
            cur = cand
        # Satu baris tunggal yang kepanjangan: potong keras.
        while measure(cur) > limit:
            cut = limit
            while cut > 1 and measure(cur[:cut]) > limit:
                cut -= max(1, cut // 8)
            chunks.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        chunks.append(cur)
    return chunks


def wa_send(phone, apikey, text):
    chunks = split_chunks(text, ENC_LIMIT,
                          measure=lambda s: len(urllib.parse.quote(s)))
    for c in chunks:
        q = urllib.parse.urlencode({"phone": phone, "text": c, "apikey": apikey})
        urllib.request.urlopen(
            "https://api.callmebot.com/whatsapp.php?" + q, timeout=45)
    return len(chunks)


def tg_post(token, chat, text):
    """Satu permintaan sendMessage. Sengaja tanpa parse_mode.
    Respons tidak pernah dibaca/dicetak: isinya menggemakan token di URL."""
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status


def tg_send(token, chat, text, pause=RETRY_PAUSE):
    """Kirim ke Telegram dengan pemecahan pesan + satu kali retry.
    4xx tidak diulang (token/chat salah tidak akan pernah berhasil)."""
    chunks = split_chunks(plain(text), TG_LIMIT)
    total = len(chunks)
    for i, c in enumerate(chunks, 1):
        body = c if total == 1 else "%s\n\n(%d/%d)" % (c, i, total)
        try:
            tg_post(token, chat, body)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise RuntimeError("Telegram menolak pesan (HTTP %d)" % e.code)
            time.sleep(pause)
            try:
                tg_post(token, chat, body)
            except Exception as e2:
                raise RuntimeError("Telegram gagal setelah retry: %s"
                                   % scrub(e2))
        except Exception as e:
            time.sleep(pause)
            try:
                tg_post(token, chat, body)
            except Exception as e2:
                raise RuntimeError("Telegram gagal setelah retry: %s"
                                   % scrub(e2))
    return total


def already_sent_today(state, channel, today):
    """Dukung format lama ({"date": ...}) maupun format per kanal."""
    if not isinstance(state, dict):
        return False
    value = (state.get(channel)
             or (state.get("date") if channel == "whatsapp" else None))
    if not value:
        return False
    try:
        return datetime.fromisoformat(value).date() == today
    except (ValueError, TypeError):
        return False


def remember(state, channel, now):
    state = dict(state) if isinstance(state, dict) else {}
    state[channel] = now.isoformat(timespec="minutes")
    state["date"] = now.isoformat(timespec="minutes")
    try:
        os.makedirs(os.path.dirname(LAST), exist_ok=True)
        with open(LAST, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError as e:
        print("Catatan pengiriman gagal disimpan:", scrub(e))
    return state


def main():
    cfg = load(os.path.join(ROOT, "config.json"), {}) or {}
    msg_path = os.path.join(ROOT, "data", "brief_message.txt")
    if not os.path.exists(msg_path):
        print("Belum ada brief_message.txt")
        return
    with open(msg_path, encoding="utf-8") as f:
        msg = f.read().strip()
    if not msg:
        print("brief_message.txt kosong, tidak ada yang dikirim.")
        return

    off = timezone(timedelta(hours=cfg.get("utc_offset_hours", 8)))
    now = datetime.now(off)
    force = setting("FORCE_SEND") == "1"
    state = load(LAST, {}) or {}

    phone = setting("WA_PHONE")
    apikey = setting("WA_APIKEY")
    token = setting("TG_TOKEN") or setting("TELEGRAM_BOT_TOKEN")
    chat = setting("TG_CHAT_ID") or setting("TELEGRAM_CHAT_ID")

    if not (phone or token):
        print("Tidak ada channel notifikasi. Pesan hanya tersimpan di file.")
        return

    # WhatsApp
    if phone and apikey:
        if not force and already_sent_today(state, "whatsapp", now.date()):
            print("WhatsApp: sudah kirim hari ini, lewati.")
        else:
            try:
                n = wa_send(phone, apikey, msg)
                state = remember(state, "whatsapp", now)
                print("WhatsApp terkirim (%d bagian)." % n)
            except Exception as e:
                print("WhatsApp gagal:", scrub(e))
    elif phone or apikey:
        print("WhatsApp: WA_PHONE / WA_APIKEY belum lengkap, dilewati.")

    # Telegram
    if token and chat:
        if not force and already_sent_today(state, "telegram", now.date()):
            print("Telegram: sudah kirim hari ini, lewati.")
        else:
            try:
                n = tg_send(token, chat, msg)
                state = remember(state, "telegram", now)
                print("Telegram terkirim (%d bagian, %d karakter)."
                      % (n, len(plain(msg))))
            except Exception as e:
                print("Telegram gagal:", scrub(e))
    elif token or chat:
        print("Telegram: TG_TOKEN / TG_CHAT_ID belum lengkap, dilewati.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # notifikasi tidak boleh membuat workflow merah
        print("Notifikasi gagal tanpa merusak workflow:", scrub(e))

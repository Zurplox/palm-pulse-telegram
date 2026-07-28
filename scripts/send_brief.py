#!/usr/bin/env python3
"""Send the Palm Pulse morning brief to Telegram.

Standalone by design. This repository never writes to palm-pulse: it only reads
the already published JSON feed over HTTP. Nothing here can affect the Palm Pulse
website, its daily workflow, or the Android app.

It exits 0 in every situation, including missing credentials, an unreachable
feed, malformed data and a Telegram outage.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "last_sent.json"


def setting(name: str, default: str) -> str:
    """An unset GitHub Actions variable arrives as an empty string, so a plain
    os.getenv(name, default) would replace the default with "" and break the
    feed URL. Fall back whenever the value is blank."""
    return (os.getenv(name) or "").strip() or default


def number(name: str, default: float) -> float:
    try:
        return float(setting(name, str(default)))
    except ValueError:
        return default


FEED_URL = setting("FEED_URL", "https://zurplox.github.io/palm-pulse/data/latest.json")
SITE_URL = setting("SITE_URL", "https://zurplox.github.io/palm-pulse/")
# Warn inside the message when the feed has not refreshed; do not go silent.
STALE_HOURS = number("STALE_HOURS", 36)
MAX_STORIES = max(1, int(number("BRIEF_STORIES", 5)))
MAX_BULLETS = max(1, int(number("BRIEF_BULLETS", 4)))
# Seconds to wait before the single retry after a rate limit or server error.
RETRY_PAUSE = number("RETRY_PAUSE", 5)
# Telegram rejects anything over 4096 characters; leave room for the footer.
LIMIT = 3800
WIB = timezone(timedelta(hours=7))
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
          "Agustus", "September", "Oktober", "November", "Desember"]
AGE_ORDER = ("5", "6", "4", "9")  # same preference the Android widget uses
USER_AGENT = "PalmPulseBrief/1.0 (+telegram morning brief)"


def parse_stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def edition_date(value) -> str:
    stamp = parse_stamp(value)
    if stamp is None:
        return "edisi terbaru"
    local = stamp.astimezone(WIB)
    return f"{local.day} {MONTHS[local.month - 1]} {local.year}"


def hours_old(value):
    stamp = parse_stamp(value)
    if stamp is None:
        return None
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 3600


def rupiah(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return "Rp" + f"{number:,.0f}".replace(",", ".")


def as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def price_value(price: dict):
    ages = price.get("age_prices_rp_per_kg") or {}
    for key in AGE_ORDER:
        if as_number(ages.get(key)) is not None:
            return ages.get(key)
    return price.get("price_rp_per_kg")


def price_line(price: dict) -> str:
    """Returns "" when there is no usable number, so the brief can never show a
    placeholder like "- Plasma: -/kg". A junk change value is dropped rather than
    raised: losing one direction arrow beats losing the whole morning brief."""
    value = as_number(price_value(price))
    if value is None:
        return ""
    change = as_number(price.get("change_rp_per_kg"))
    detail = ""
    if change:
        detail = f" ({'naik' if change > 0 else 'turun'} {rupiah(abs(change))})"
    return f"- {price.get('scheme') or 'TBS'}: {rupiah(value)}/kg{detail}"


def fetch_edition(url: str = "") -> dict:
    target = url or FEED_URL
    response = requests.get(
        target,
        params={"t": int(datetime.now(timezone.utc).timestamp())},
        headers={"Cache-Control": "no-cache", "User-Agent": USER_AGENT},
        timeout=25,
    )
    response.raise_for_status()
    return response.json()


def build_message(data: dict) -> str:
    """Plain text on purpose: with no parse_mode, a headline containing an
    underscore, asterisk or bracket can never break the message. Telegram
    auto-links bare URLs."""
    lines = [f"PALM PULSE - Brief pagi {edition_date(data.get('generated_at'))}"]

    summary = str(data.get("master_summary") or "")
    bullets = [line.strip().lstrip("-").lstrip("\u2022").strip()
               for line in summary.splitlines()
               if line.strip().startswith("-") or line.strip().startswith("\u2022")]
    if bullets:
        lines += ["", "RINGKASAN"] + [f"- {bullet}" for bullet in bullets[:MAX_BULLETS]]

    prices = [p for p in (data.get("tbs_prices") or []) if isinstance(p, dict)]
    price_lines = [line for line in (price_line(price) for price in prices[:3]) if line]
    if price_lines:
        head = prices[0]
        region = str(head.get("region") or "").strip().upper()
        # Never print the word None: omit whatever the feed did not supply.
        heading = " ".join(part for part in ("HARGA TBS", region) if part)
        if head.get("valid_from") and head.get("valid_to"):
            heading += f" ({head['valid_from']} s/d {head['valid_to']})"
        lines += ["", heading] + price_lines

    stories = [s for s in (data.get("stories") or []) if isinstance(s, dict)]
    if stories:
        lines += ["", "BERITA UTAMA"]
        for index, story in enumerate(stories[:MAX_STORIES], start=1):
            lines.append(f"{index}. {story.get('title')} ({story.get('source')})")
            if story.get("url"):
                lines.append(f"   {story['url']}")

    age = hours_old(data.get("generated_at"))
    if age is not None and age > STALE_HOURS:
        lines += ["", f"Catatan: edisi ini berumur {age:.0f} jam, feed belum diperbarui."]

    lines += ["", f"Selengkapnya: {SITE_URL}"]
    text = "\n".join(lines)
    if len(text) > LIMIT:
        text = text[:LIMIT].rsplit("\n", 1)[0] + "\n..."
    return text


def last_sent():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("generated_at")
    except Exception:
        return None


def remember(generated_at) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "generated_at": generated_at,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"WARNING: could not record state ({type(exc).__name__}).", file=sys.stderr)


def deliver(endpoint: str, payload: dict) -> bool:
    """Send with one bounded retry. A rate limit or a server hiccup is usually
    transient, and the brief is only worth sending once per morning. Never print
    the response body: Telegram echoes the request, which carries the token."""
    for attempt in (1, 2):
        try:
            response = requests.post(endpoint, timeout=25, json=payload)
        except Exception as exc:
            print(f"WARNING: Telegram delivery failed ({type(exc).__name__}), attempt {attempt}.",
                  file=sys.stderr)
        else:
            if response.status_code == 200:
                return True
            print(f"WARNING: Telegram rejected the message (HTTP {response.status_code}), "
                  f"attempt {attempt}.", file=sys.stderr)
            # A bad token or a wrong chat id will never succeed; do not retry.
            if response.status_code != 429 and response.status_code < 500:
                return False
        if attempt == 1:
            time.sleep(RETRY_PAUSE)
    return False


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram credentials are not set; skipping delivery.", file=sys.stderr)
        return 0
    try:
        data = fetch_edition()
    except Exception as exc:
        print(f"WARNING: could not read the Palm Pulse feed ({type(exc).__name__}).", file=sys.stderr)
        return 0
    if not isinstance(data, dict) or not data.get("stories"):
        print("WARNING: the feed has no stories; nothing to send.", file=sys.stderr)
        return 0

    generated_at = data.get("generated_at")
    forced = os.getenv("FORCE_SEND", "").strip().lower() in {"1", "true", "yes"}
    if not forced and generated_at and generated_at == last_sent():
        print(f"Edition {generated_at} was already sent; skipping.")
        return 0

    try:
        text = build_message(data)
    except Exception as exc:
        print(f"WARNING: could not build the brief ({type(exc).__name__}).", file=sys.stderr)
        return 0

    endpoint = "https://api.telegram.org/bot" + token + "/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if deliver(endpoint, payload):
        print(f"Morning brief sent ({len(text)} characters) for edition {generated_at}.")
        remember(generated_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())

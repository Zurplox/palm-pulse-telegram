# palm-pulse-telegram

Sends the **Palm Pulse morning brief** to Telegram every morning.

This repository is deliberately separate from
[palm-pulse](https://github.com/Zurplox/palm-pulse). It only **reads** the
published feed over HTTPS:

```
https://zurplox.github.io/palm-pulse/data/latest.json
```

It never writes to that repository, never touches the website, and never runs
as part of the daily build. If this repo breaks, Palm Pulse and the Android app
keep working exactly as before.

## Setup (about five minutes)

1. **Create the bot.** In Telegram, message [@BotFather](https://t.me/BotFather),
   send `/newbot`, pick a name and a username. BotFather replies with a token
   that looks like `123456789:AAE...`. Keep it private.
2. **Start a chat with your bot** and send it any message (a bot cannot message
   you first).
3. **Get your chat id.** Message [@userinfobot](https://t.me/userinfobot); it
   replies with your numeric id. For a group, add the bot to the group and use
   the group id (it starts with `-`).
4. **Add the two secrets.** In this repo: *Settings -> Secrets and variables ->
   Actions -> New repository secret*.

   | Secret | Value |
   | --- | --- |
   | `TELEGRAM_BOT_TOKEN` | the token from BotFather |
   | `TELEGRAM_CHAT_ID` | your numeric chat id |

5. **Test it.** *Actions -> Palm Pulse morning brief -> Run workflow*, tick
   **force**, and run. The brief should arrive within seconds.

Without those two secrets the workflow still succeeds and simply logs
`Telegram credentials are not set; skipping delivery.`

## Optional settings

Repository *variables* (not secrets), all optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FEED_URL` | Palm Pulse `latest.json` | point at a different feed |
| `SITE_URL` | Palm Pulse site | the link in the footer |
| `STALE_HOURS` | `36` | when to add a "feed not refreshed" note |
| `RETRY_PAUSE` | `5` | seconds to wait before the single retry |
| `BRIEF_STORIES` | `5` | how many headlines to include |
| `BRIEF_BULLETS` | `4` | how many summary bullets to include |

Leaving a variable unset is safe: blank values fall back to the defaults.

## Schedule

`15 23 * * *` UTC = **06:15 WIB / 07:15 Singapore**, chosen because Palm Pulse
starts at 22:30 UTC and finishes in roughly 21 minutes, so the feed is fresh.
If you change the Palm Pulse cron, change this one too.

## What the brief contains

```
PALM PULSE - Brief pagi 28 Juli 2026

RINGKASAN
- ...up to four bullets from the AI summary

HARGA TBS RIAU (2026-07-22 s/d 2026-07-28)
- Swadaya: Rp3.640/kg (naik Rp40)

BERITA UTAMA
1. Headline (Source)
   https://...

Selengkapnya: https://zurplox.github.io/palm-pulse/
```

The price uses the same age preference as the Android widget (age 5, then 6, 4, 9).

## Design guarantees

- **Plain text, no `parse_mode`.** A headline containing `*`, `_`, `[` or `(`
  can never break the message. Telegram still auto-links bare URLs.
- **Always exits 0.** Missing credentials, unreachable feed, malformed JSON,
  Telegram outage or rate limit all log a warning instead of failing the run,
  so you never get red-X emails.
- **One retry on transient failures.** A rate limit (429), a server error (5xx)
  or a dropped connection is retried once after `RETRY_PAUSE` seconds. A bad
  token or wrong chat id (4xx) is never retried, because it can never succeed.
- **Bad price data costs a line, never the brief.** A scheme with an unusable
  number is skipped, a junk change value drops the direction arrow, and missing
  region or dates are simply omitted. The word `None` is never printed.
- **Recording the sent edition cannot fail the run.** That step is
  `continue-on-error`, so a protected branch or a push race never turns the run
  red after the brief has already been delivered.
- **No duplicates.** The edition timestamp that was sent is recorded in
  `state/last_sent.json`, so a re-run does not resend the same brief. Use the
  **force** input to override.
- **Stale feed is flagged, not hidden.** If the feed has not refreshed in
  `STALE_HOURS`, the brief still arrives with a note about its age.
- **The token is never printed.** Telegram error responses echo the request, so
  only the status code is logged.

## Run it locally

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... FORCE_SEND=1
python scripts/send_brief.py
```

## Tests

```bash
python -m unittest discover -s scripts/tests
```

39 tests, no network access in any of them. They cover message formatting, the
WIB date boundary, the Telegram character cap, the retry rules, the duplicate
guard, malformed price data, and blank-variable fallbacks.

The workflow runs the suite **before** sending, so a broken change stops the
brief instead of delivering something wrong. That is deliberate: the tests are
hermetic and deterministic, so they cannot fail for environmental reasons.

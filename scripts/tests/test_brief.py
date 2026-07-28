import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import send_brief as sb


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def edition(**overrides) -> dict:
    data = {
        "generated_at": ago(1),
        "master_summary": "RINGKASAN EKSEKUTIF\n- Harga CPO menguat pekan ini.\n- Ekspor India naik.\n- Stok Malaysia turun.\n- Cuaca Riau membaik.\n- Bullet kelima harus dipotong.",
        "stories": [
            {"title": "Harga TBS Riau naik", "url": "https://example.com/a", "source": "InfoSAWIT"},
            {"title": "CPO futures climb", "url": "https://example.com/b", "source": "Reuters"},
        ],
        "tbs_prices": [{
            "region": "Riau", "scheme": "Swadaya", "valid_from": "2026-07-22", "valid_to": "2026-07-28",
            "price_rp_per_kg": 3500, "change_rp_per_kg": 39.58,
            "age_prices_rp_per_kg": {"5": 3639.59, "9": 3930.55},
        }],
    }
    data.update(overrides)
    return data


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class BriefFormatting(unittest.TestCase):
    def test_brief_carries_the_essentials(self):
        text = sb.build_message(edition())
        self.assertIn("PALM PULSE - Brief pagi", text)
        self.assertIn("RINGKASAN", text)
        self.assertIn("Harga CPO menguat pekan ini.", text)
        self.assertIn("HARGA TBS RIAU (2026-07-22 s/d 2026-07-28)", text)
        self.assertIn("BERITA UTAMA", text)
        self.assertIn("https://example.com/a", text)
        self.assertIn("Selengkapnya:", text)

    def test_only_four_bullets_are_carried(self):
        text = sb.build_message(edition())
        self.assertNotIn("Bullet kelima", text)

    def test_price_prefers_age_five_and_shows_direction(self):
        text = sb.build_message(edition())
        self.assertIn("Rp3.640/kg", text)  # age 5, the widget's first choice
        self.assertIn("naik", text)

    def test_headline_punctuation_is_never_escaped(self):
        data = edition(stories=[{"title": "B50 *bold* _under_ [x] (y)", "url": "https://e.com/1", "source": "X"}])
        self.assertIn("B50 *bold* _under_ [x] (y)", sb.build_message(data))

    def test_edition_date_is_the_morning_it_lands_in_riau(self):
        # 22:30 UTC on 27 July is 05:30 WIB on 28 July.
        self.assertEqual(sb.edition_date("2026-07-27T22:30:00+00:00"), "28 Juli 2026")

    def test_missing_sections_are_skipped_not_faked(self):
        text = sb.build_message({"generated_at": ago(1), "stories": [{"title": "T", "url": "", "source": "S"}]})
        self.assertNotIn("HARGA TBS", text)
        self.assertNotIn("RINGKASAN", text)
        self.assertIn("BERITA UTAMA", text)

    def test_unparseable_timestamp_does_not_raise(self):
        text = sb.build_message(edition(generated_at="not a date"))
        self.assertIn("edisi terbaru", text)

    def test_empty_edition_still_produces_a_safe_message(self):
        text = sb.build_message({})
        self.assertIn("PALM PULSE", text)
        self.assertTrue(text.strip())

    def test_long_edition_stays_within_the_telegram_limit(self):
        stories = [{"title": "x" * 1200, "url": "https://e.com/" + str(i), "source": "S"} for i in range(5)]
        text = sb.build_message(edition(stories=stories))
        self.assertLessEqual(len(text), sb.LIMIT + 4)
        self.assertTrue(text.endswith("..."))

    def test_stale_feed_is_flagged_inside_the_message(self):
        text = sb.build_message(edition(generated_at=ago(50)))
        self.assertIn("feed belum diperbarui", text)

    def test_fresh_feed_carries_no_stale_note(self):
        self.assertNotIn("belum diperbarui", sb.build_message(edition(generated_at=ago(2))))


class DeliveryNeverFails(unittest.TestCase):
    def setUp(self):
        self.saved = {
            "state": sb.STATE,
            "post": sb.requests.post,
            "get": sb.requests.get,
            "sleep": sb.time.sleep,
            "token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "chat": os.environ.get("TELEGRAM_CHAT_ID"),
            "force": os.environ.get("FORCE_SEND"),
        }
        self.tmp = tempfile.TemporaryDirectory()
        sb.STATE = Path(self.tmp.name) / "state" / "last_sent.json"
        os.environ["TELEGRAM_BOT_TOKEN"] = "token-123"
        os.environ["TELEGRAM_CHAT_ID"] = "chat-456"
        os.environ.pop("FORCE_SEND", None)
        # Never really sleep through the retry pause in a test run.
        sb.time.sleep = lambda seconds: None
        self.posted = []
        # One fixed payload: if the fake feed rebuilt its timestamp on every
        # call, the duplicate-guard tests would silently test nothing.
        self.payload = edition()
        sb.requests.post = lambda url, **kw: self.posted.append((url, kw)) or FakeResponse(200)
        sb.requests.get = lambda url, **kw: FakeResponse(200, self.payload)

    def tearDown(self):
        sb.STATE = self.saved["state"]
        sb.requests.post = self.saved["post"]
        sb.requests.get = self.saved["get"]
        sb.time.sleep = self.saved["sleep"]
        for key, name in (("token", "TELEGRAM_BOT_TOKEN"), ("chat", "TELEGRAM_CHAT_ID"), ("force", "FORCE_SEND")):
            if self.saved[key] is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = self.saved[key]
        self.tmp.cleanup()

    def test_happy_path_posts_plain_text_to_the_configured_chat(self):
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 1)
        url, kwargs = self.posted[0]
        self.assertTrue(url.startswith("https://api.telegram.org/bot"))
        self.assertEqual(kwargs["json"]["chat_id"], "chat-456")
        self.assertNotIn("parse_mode", kwargs["json"])

    def test_without_credentials_it_no_ops_without_touching_the_network(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = ""
        def explode(*a, **k):
            raise AssertionError("must not touch the network")
        sb.requests.get = explode
        sb.requests.post = explode
        self.assertEqual(sb.main(), 0)

    def test_unreachable_feed_returns_zero_and_sends_nothing(self):
        def explode(*a, **k):
            raise RuntimeError("dns failure")
        sb.requests.get = explode
        self.assertEqual(sb.main(), 0)
        self.assertEqual(self.posted, [])

    def test_feed_without_stories_sends_nothing(self):
        sb.requests.get = lambda url, **kw: FakeResponse(200, {"generated_at": ago(1), "stories": []})
        self.assertEqual(sb.main(), 0)
        self.assertEqual(self.posted, [])

    def test_corrupt_feed_returns_zero(self):
        def bad_json(*a, **k):
            raise ValueError("not json")
        sb.requests.get = lambda url, **kw: type("R", (), {"status_code": 200, "raise_for_status": lambda s: None, "json": bad_json})()
        self.assertEqual(sb.main(), 0)
        self.assertEqual(self.posted, [])

    def test_network_failure_on_send_returns_zero(self):
        def explode(*a, **k):
            raise RuntimeError("telegram down")
        sb.requests.post = explode
        self.assertEqual(sb.main(), 0)

    def test_rejected_message_returns_zero_and_is_not_recorded(self):
        sb.requests.post = lambda url, **kw: FakeResponse(429)
        self.assertEqual(sb.main(), 0)
        self.assertIsNone(sb.last_sent())

    def test_a_rate_limit_is_retried_once_and_then_succeeds(self):
        codes = [429, 200]
        def flaky(url, **kw):
            self.posted.append((url, kw))
            return FakeResponse(codes.pop(0))
        sb.requests.post = flaky
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 2, "a 429 must be retried once")
        self.assertIsNotNone(sb.last_sent(), "the retried success must be recorded")

    def test_a_server_error_is_retried_once(self):
        def failing(url, **kw):
            self.posted.append((url, kw))
            return FakeResponse(503)
        sb.requests.post = failing
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 2)
        self.assertIsNone(sb.last_sent())

    def test_a_bad_token_is_not_retried(self):
        def unauthorised(url, **kw):
            self.posted.append((url, kw))
            return FakeResponse(401)
        sb.requests.post = unauthorised
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 1, "a permanent error must not be retried")

    def test_a_network_failure_is_retried_once(self):
        attempts = []
        def explode(*a, **k):
            attempts.append(1)
            raise RuntimeError("telegram down")
        sb.requests.post = explode
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(attempts), 2)

    def test_the_same_edition_is_never_sent_twice(self):
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 1, "a repeat run must not resend the same edition")

    def test_a_new_edition_is_sent_again(self):
        self.assertEqual(sb.main(), 0)
        fresher = edition(generated_at=ago(0.1))
        sb.requests.get = lambda url, **kw: FakeResponse(200, fresher)
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 2)

    def test_force_send_overrides_the_duplicate_guard(self):
        self.assertEqual(sb.main(), 0)
        os.environ["FORCE_SEND"] = "true"
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 2)

    def test_unwritable_state_does_not_break_delivery(self):
        sb.STATE = Path("/proc/definitely-not-writable/last_sent.json")
        self.assertEqual(sb.main(), 0)
        self.assertEqual(len(self.posted), 1)

    def test_state_records_the_edition_that_was_sent(self):
        self.assertEqual(sb.main(), 0)
        saved = json.loads(sb.STATE.read_text(encoding="utf-8"))
        self.assertIn("generated_at", saved)
        self.assertIn("sent_at", saved)

    def test_the_feed_is_requested_with_cache_busting(self):
        seen = {}
        payload = self.payload
        def capture(url, **kw):
            seen["url"] = url
            seen.update(kw)
            return FakeResponse(200, payload)
        sb.requests.get = capture
        self.assertEqual(sb.main(), 0)
        self.assertIn("t", seen["params"])
        self.assertEqual(seen["headers"]["Cache-Control"], "no-cache")

    def test_it_reads_palm_pulse_over_http_and_never_writes_to_it(self):
        self.assertEqual(sb.main(), 0)
        self.assertIn("palm-pulse", sb.FEED_URL)
        self.assertTrue(sb.FEED_URL.startswith("https://"))
        self.assertIn("latest.json", sb.FEED_URL)


class MalformedPriceDataCannotCostTheBrief(unittest.TestCase):
    """Every one of these used to either crash the brief or print a placeholder."""

    def test_junk_change_value_does_not_lose_the_brief(self):
        data = edition(tbs_prices=[{"region": "Riau", "scheme": "Swadaya", "price_rp_per_kg": 3500,
                                    "change_rp_per_kg": "tidak tersedia",
                                    "valid_from": "2026-07-22", "valid_to": "2026-07-28"}])
        text = sb.build_message(data)
        self.assertIn("BERITA UTAMA", text)
        # Assert on the price line itself: a story headline in the fixture also
        # contains the word "naik", so a whole-message check proves nothing.
        price_lines = [line for line in text.splitlines() if "/kg" in line]
        self.assertEqual(price_lines, ["- Swadaya: Rp3.500/kg"])

    def test_missing_region_and_period_never_print_none(self):
        data = edition(tbs_prices=[{"scheme": "Umum", "price_rp_per_kg": 3100}])
        text = sb.build_message(data)
        self.assertNotIn("None", text)
        self.assertIn("HARGA TBS", text)
        self.assertIn("Rp3.100/kg", text)

    def test_price_without_any_number_is_skipped_entirely(self):
        data = edition(tbs_prices=[{"region": "Riau", "scheme": "Plasma",
                                    "price_rp_per_kg": None, "age_prices_rp_per_kg": {}}])
        text = sb.build_message(data)
        self.assertNotIn("HARGA TBS", text)
        self.assertNotIn("/kg", text)

    def test_a_usable_scheme_survives_an_unusable_one(self):
        data = edition(tbs_prices=[
            {"region": "Riau", "scheme": "Plasma", "price_rp_per_kg": "n/a"},
            {"region": "Riau", "scheme": "Swadaya", "price_rp_per_kg": 3400},
        ])
        text = sb.build_message(data)
        self.assertIn("Swadaya: Rp3.400/kg", text)
        self.assertNotIn("Plasma", text)

    def test_string_prices_from_the_feed_are_accepted(self):
        data = edition(tbs_prices=[{"region": "Riau", "scheme": "Swadaya",
                                    "age_prices_rp_per_kg": {"5": "3639.59"},
                                    "change_rp_per_kg": "-12.5"}])
        text = sb.build_message(data)
        self.assertIn("Rp3.640/kg", text)
        # 12.5 rounds to 12, not 13: Python rounds half to even.
        self.assertIn("turun Rp12", text)

    def test_non_dict_entries_in_the_price_list_are_ignored(self):
        data = edition(tbs_prices=["junk", None, {"scheme": "Umum", "price_rp_per_kg": 3000}])
        self.assertIn("Rp3.000/kg", sb.build_message(data))


class HelpersDirectly(unittest.TestCase):
    """These were only covered indirectly through build_message and main."""

    def test_rupiah_uses_indonesian_thousand_separators(self):
        self.assertEqual(sb.rupiah(3639.59), "Rp3.640")
        self.assertEqual(sb.rupiah(1234567), "Rp1.234.567")
        self.assertEqual(sb.rupiah(0), "Rp0")

    def test_rupiah_returns_a_dash_for_junk(self):
        for bad in (None, "", "n/a", {}, []):
            self.assertEqual(sb.rupiah(bad), "-")

    def test_as_number_accepts_strings_and_rejects_junk(self):
        self.assertEqual(sb.as_number("3400"), 3400.0)
        self.assertEqual(sb.as_number(-12.5), -12.5)
        for bad in (None, "", "tidak ada", {}):
            self.assertIsNone(sb.as_number(bad))

    def test_parse_stamp_handles_every_format_the_feed_uses(self):
        for value in ("2026-07-27T22:30:00Z", "2026-07-27T22:30:00.123Z",
                      "2026-07-27T22:30:00+00:00", "2026-07-27 22:30:00", "2026-07-27"):
            self.assertIsNotNone(sb.parse_stamp(value), f"{value} must parse")

    def test_parse_stamp_returns_none_for_junk_instead_of_raising(self):
        for bad in (None, "", "kemarin", 12345, {}):
            self.assertIsNone(sb.parse_stamp(bad))

    def test_a_naive_timestamp_is_treated_as_utc(self):
        self.assertEqual(sb.parse_stamp("2026-07-27 22:30:00").utcoffset().total_seconds(), 0)

    def test_hours_old_measures_age_and_tolerates_junk(self):
        self.assertAlmostEqual(sb.hours_old(ago(5)), 5, delta=0.1)
        self.assertIsNone(sb.hours_old("kemarin"))

    def test_price_value_follows_the_android_widget_age_order(self):
        ages = {"4": 3400, "5": 3639, "6": 3700, "9": 3930}
        self.assertEqual(sb.price_value({"age_prices_rp_per_kg": ages}), 3639)
        self.assertEqual(sb.price_value({"age_prices_rp_per_kg": {"9": 3930, "4": 3400}}), 3400)
        self.assertEqual(sb.price_value({"age_prices_rp_per_kg": {"9": 3930}}), 3930)

    def test_price_value_falls_back_to_the_flat_price(self):
        self.assertEqual(sb.price_value({"price_rp_per_kg": 3100}), 3100)
        self.assertEqual(sb.price_value({"age_prices_rp_per_kg": {"5": "kosong"},
                                         "price_rp_per_kg": 3100}), 3100)

    def test_fetch_edition_asks_for_the_feed_with_a_timeout_and_no_cache(self):
        seen = {}
        saved = sb.requests.get
        sb.requests.get = lambda url, **kw: seen.update({"url": url, **kw}) or FakeResponse(200, {"ok": 1})
        try:
            self.assertEqual(sb.fetch_edition(), {"ok": 1})
        finally:
            sb.requests.get = saved
        self.assertEqual(seen["url"], sb.FEED_URL)
        self.assertEqual(seen["timeout"], 25)
        self.assertIn("t", seen["params"])
        self.assertEqual(seen["headers"]["Cache-Control"], "no-cache")

    def test_fetch_edition_raises_on_an_http_error_so_main_can_catch_it(self):
        saved = sb.requests.get
        sb.requests.get = lambda url, **kw: FakeResponse(404)
        try:
            with self.assertRaises(Exception):
                sb.fetch_edition()
        finally:
            sb.requests.get = saved

    def test_remember_round_trips_the_edition_stamp(self):
        saved = sb.STATE
        with tempfile.TemporaryDirectory() as tmp:
            sb.STATE = Path(tmp) / "deep" / "state" / "last_sent.json"
            try:
                sb.remember("2026-07-27T22:30:00Z")
                self.assertEqual(sb.last_sent(), "2026-07-27T22:30:00Z")
                written = json.loads(sb.STATE.read_text(encoding="utf-8"))
                self.assertIsNotNone(written["sent_at"])
            finally:
                sb.STATE = saved

    def test_last_sent_is_none_when_the_state_file_is_corrupt(self):
        saved = sb.STATE
        with tempfile.TemporaryDirectory() as tmp:
            sb.STATE = Path(tmp) / "last_sent.json"
            sb.STATE.write_text("{not json", encoding="utf-8")
            try:
                self.assertIsNone(sb.last_sent())
            finally:
                sb.STATE = saved


class BlankSettingsFallBackToDefaults(unittest.TestCase):
    """GitHub passes an unset repository variable as an empty string, which is
    exactly how a working feed URL turns into ""."""

    def setUp(self):
        self.saved = {name: os.environ.get(name)
                      for name in ("FEED_URL", "SITE_URL", "STALE_HOURS", "BRIEF_STORIES")}

    def tearDown(self):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_blank_url_variable_falls_back(self):
        os.environ["FEED_URL"] = ""
        self.assertIn("palm-pulse", sb.setting("FEED_URL", "https://zurplox.github.io/palm-pulse/data/latest.json"))

    def test_whitespace_only_variable_falls_back(self):
        os.environ["SITE_URL"] = "   "
        self.assertEqual(sb.setting("SITE_URL", "https://fallback/"), "https://fallback/")

    def test_a_real_value_is_honoured(self):
        os.environ["FEED_URL"] = "https://example.com/feed.json"
        self.assertEqual(sb.setting("FEED_URL", "https://fallback/"), "https://example.com/feed.json")

    def test_blank_and_junk_numbers_fall_back(self):
        os.environ["STALE_HOURS"] = ""
        self.assertEqual(sb.number("STALE_HOURS", 36), 36)
        os.environ["BRIEF_STORIES"] = "not a number"
        self.assertEqual(sb.number("BRIEF_STORIES", 5), 5)


if __name__ == "__main__":
    unittest.main()

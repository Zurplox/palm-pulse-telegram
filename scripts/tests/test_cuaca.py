#!/usr/bin/env python3
"""Tes offline untuk scripts/cuaca.py (feed kebun-sawit-cuaca). Tanpa jaringan.

Bentuk data mengikuti data/cuaca.json + data/lingkungan.json milik repo cuaca.
Jalankan: python -m unittest discover -s scripts/tests
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import cuaca  # noqa: E402

CFG = {"cuaca": {"stale_hours": 24, "forecast_days": 3}}

CUACA = {
    "updated_at": "2026-07-28T08:56+08:00",
    "farm_name": "Kebun Sawit (Rawang Air Putih)",
    "today": {"date": "2026-07-28", "precip": 0.4, "prob": 24, "tmax": 30.8,
              "tmin": 24.4, "condition": "Gerimis ringan", "emoji": "\U0001F326",
              "wind": 13.6, "gust": 28.4, "wind_dir": "Tenggara"},
    "days": [
        {"date": "2026-07-27", "precip": 2.0, "prob": 51, "kind": "actual"},
        {"date": "2026-07-28", "precip": 0.4, "prob": 24, "kind": "forecast"},
        {"date": "2026-07-29", "precip": 5.1, "prob": 62, "kind": "forecast"},
        {"date": "2026-07-30", "precip": 0.0, "prob": 18, "kind": "forecast"},
        {"date": "2026-07-31", "precip": 12.0, "prob": 80, "kind": "forecast"},
    ],
}

LING = {
    "updated_at": "2026-07-28T08:56+08:00",
    "fire": {"status": "waspada", "count_within": 1,
             "nearest": {"km": 42.1, "dir": "selatan",
                         "place": "Pangkalan Kerinci, Pelalawan"}},
    "air": {"us_aqi": 63, "category": "Sedang", "haze": "berkabut tipis"},
    "flood": {"river_discharge": 272.5, "unit": "m3/s", "trend": "turun",
              "status": "Normal"},
}

NOW = datetime(2026, 7, 28, 3, 0, tzinfo=timezone.utc)  # 10:00 SGT


class Helpers(unittest.TestCase):
    def test_num_parses_and_rejects(self):
        self.assertEqual(cuaca.num("3.5"), 3.5)
        self.assertIsNone(cuaca.num("x"))
        self.assertIsNone(cuaca.num(None))

    def test_trim_drops_trailing_zero(self):
        self.assertEqual(cuaca.trim(25.0), "25")
        self.assertEqual(cuaca.trim(0.4), "0.4")
        self.assertIsNone(cuaca.trim("x"))

    def test_hours_old_handles_offset_timestamp(self):
        # 08:56+08:00 = 00:56 UTC; jam 03:00 UTC berarti ~2 jam.
        self.assertAlmostEqual(
            cuaca.hours_old("2026-07-28T08:56+08:00", NOW), 2.066, places=2)

    def test_hours_old_junk_is_none(self):
        self.assertIsNone(cuaca.hours_old("besok"))
        self.assertIsNone(cuaca.hours_old(None))


class WeatherBlock(unittest.TestCase):
    def setUp(self):
        self.block = cuaca.weather_block(CUACA, CFG, NOW)

    def test_heading_has_farm_name(self):
        self.assertIn("Cuaca kebun", self.block)
        self.assertIn("Rawang Air Putih", self.block)

    def test_today_line_has_condition_rain_and_temps(self):
        self.assertIn("Gerimis ringan", self.block)
        self.assertIn("hujan 0.4 mm (peluang 24%)", self.block)
        self.assertIn("24.4\u201330.8\u00b0C", self.block)

    def test_wind_line(self):
        self.assertIn("Angin Tenggara 13.6 km/jam", self.block)
        self.assertIn("hembusan 28.4", self.block)

    def test_forecast_skips_today_and_actuals(self):
        self.assertIn("Prakiraan:", self.block)
        self.assertNotIn("2026-07-27", self.block)  # actual
        self.assertNotIn("  2026-07-28:", self.block)  # hari ini
        self.assertIn("2026-07-29: 5.1 mm, 62%", self.block)

    def test_forecast_respects_limit(self):
        self.assertIn("2026-07-31", self.block)
        block = cuaca.weather_block(CUACA, {"cuaca": {"forecast_days": 1}}, NOW)
        self.assertIn("2026-07-29", block)
        self.assertNotIn("2026-07-31", block)

    def test_fresh_feed_has_no_stale_note(self):
        self.assertNotIn("belum diperbarui", self.block)

    def test_stale_feed_gets_note(self):
        late = datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)
        self.assertIn("belum diperbarui",
                      cuaca.weather_block(CUACA, CFG, late))


class EnvBlock(unittest.TestCase):
    def setUp(self):
        self.block = cuaca.env_block(LING, CFG)

    def test_flood_line(self):
        self.assertIn("Banjir: Normal", self.block)
        self.assertIn("debit 272.5 m3/s", self.block)
        self.assertIn("turun", self.block)

    def test_fire_line(self):
        self.assertIn("Karhutla: waspada", self.block)
        self.assertIn("42.1 km selatan", self.block)
        self.assertIn("Pangkalan Kerinci", self.block)

    def test_air_line(self):
        self.assertIn("Udara: AQI 63, Sedang, berkabut tipis", self.block)


class MalformedFeedCannotCostTheBrief(unittest.TestCase):
    """Feed cuaca diperlakukan sama tidak tepercayanya dengan feed Palm Pulse."""

    def test_non_dict_feeds_are_survivable(self):
        self.assertEqual(cuaca.weather_block("rusak", CFG), "")
        self.assertEqual(cuaca.weather_block(None, CFG), "")
        self.assertEqual(cuaca.env_block("rusak", CFG), "")
        self.assertEqual(cuaca.env_block(None, CFG), "")

    def test_empty_feeds_drop_the_section(self):
        self.assertEqual(cuaca.weather_block({}, CFG), "")
        self.assertEqual(cuaca.env_block({}, CFG), "")

    def test_today_not_a_dict_is_survivable(self):
        self.assertEqual(cuaca.weather_block({"today": "rusak"}, CFG), "")

    def test_days_not_a_list_is_survivable(self):
        block = cuaca.weather_block({"today": {"condition": "Cerah"},
                                     "days": "rusak"}, CFG)
        self.assertIn("Cerah", block)
        self.assertNotIn("Prakiraan", block)

    def test_string_numbers_do_not_raise(self):
        data = {"today": {"condition": "Hujan", "precip": "banyak",
                          "prob": "tinggi", "tmax": "panas", "tmin": None,
                          "wind": "kencang"}}
        block = cuaca.weather_block(data, CFG)
        self.assertIn("Hujan", block)
        self.assertNotIn("None", block)

    def test_never_prints_the_word_none(self):
        messy = {"updated_at": None, "farm_name": None,
                 "today": {"condition": None, "precip": None, "prob": 30,
                           "tmax": None, "tmin": None, "wind": None,
                           "emoji": None},
                 "days": [{"date": None, "precip": None}]}
        self.assertNotIn("None", cuaca.weather_block(messy, CFG))

    def test_partial_environment_keeps_what_works(self):
        block = cuaca.env_block({"flood": "rusak", "fire": None,
                                 "air": {"us_aqi": 63}}, CFG)
        self.assertIn("Udara: AQI 63", block)
        self.assertNotIn("Banjir:", block)
        self.assertNotIn("Karhutla:", block)

    def test_fire_without_nearest_still_shows_status(self):
        block = cuaca.env_block({"fire": {"status": "aman"}}, CFG)
        self.assertIn("Karhutla: aman", block)

    def test_flood_without_status_uses_dash(self):
        block = cuaca.env_block({"flood": {"river_discharge": 100}}, CFG)
        self.assertIn("Banjir: -", block)
        self.assertIn("debit 100", block)


if __name__ == "__main__":
    unittest.main()

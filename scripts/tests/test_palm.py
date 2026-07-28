#!/usr/bin/env python3
"""Tes offline untuk scripts/palm.py + build_brief. Tanpa jaringan.

Jalankan: python -m unittest discover -s scripts/tests
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import palm  # noqa: E402
import build_brief as bb  # noqa: E402

CFG = {"brief_title": "BRIEF PAGI", "emoji": "\U0001F4F0",
       "utc_offset_hours": 8,
       "palm": {"stale_hours": 36, "max_bullets": 4, "max_stories": 8,
                "site_url": "https://zurplox.github.io/palm-pulse/"},
       "cuaca": {"stale_hours": 24, "forecast_days": 3,
                 "site_url": "https://zurplox.github.io/kebun-sawit-cuaca/"}}

FEED = {
    "generated_at": "2026-07-27T22:30:00Z",
    "master_summary": "Ikhtisar:\n- Harga TBS Riau naik tipis.\n"
                      "- CPO Bursa Malaysia melemah.\n"
                      "\u2022 B50 masih dibahas.\nPenutup tanpa peluru.",
    "tbs_prices": [
        {"region": "riau", "scheme": "Plasma", "valid_from": "2026-07-22",
         "valid_to": "2026-07-28", "age_prices_rp_per_kg": {"5": 3640},
         "change_rp_per_kg": 40},
        {"region": "riau", "scheme": "Swadaya", "price_rp_per_kg": 3564,
         "change_rp_per_kg": -13},
    ],
    "stories": [{"title": "Judul Palm Pulse", "source": "infosawit",
                 "url": "https://example.com/a"},
                {"title": "Berita kedua", "source": "elaeis",
                 "url": "https://example.com/b"}],
}

MARKETS = {"tickers": [{"label": "VOO (S&P 500)", "last": 679.31,
                        "pct": -0.43}],
           "fx": [{"pair": "USD/IDR", "rate": 17990}]}


class Helpers(unittest.TestCase):
    def test_rupiah_indonesian_separator(self):
        self.assertEqual(palm.rupiah(3640), "Rp3.640")

    def test_rupiah_handles_junk(self):
        self.assertEqual(palm.rupiah("abc"), "-")
        self.assertEqual(palm.rupiah(None), "-")

    def test_rupiah_banker_rounding_documented(self):
        # Python membulatkan setengah ke genap: 12.5 -> Rp12, bukan Rp13.
        self.assertEqual(palm.rupiah(12.5), "Rp12")

    def test_as_number(self):
        self.assertEqual(palm.as_number("3.5"), 3.5)
        self.assertIsNone(palm.as_number("x"))
        self.assertIsNone(palm.as_number(None))

    def test_edition_date_uses_wib_next_day(self):
        # Edisi 22:30 UTC = 05:30 WIB keesokan harinya.
        self.assertEqual(palm.edition_date("2026-07-27T22:30:00Z"),
                         "28 Juli 2026")

    def test_edition_date_junk_is_none(self):
        self.assertIsNone(palm.edition_date("bukan tanggal"))
        self.assertIsNone(palm.edition_date(None))

    def test_hours_old(self):
        now = datetime(2026, 7, 28, 22, 30, tzinfo=timezone.utc)
        self.assertAlmostEqual(
            palm.hours_old("2026-07-27T22:30:00Z", now), 24.0, places=3)

    def test_price_value_prefers_age_five(self):
        price = {"age_prices_rp_per_kg": {"4": 100, "5": 200, "9": 300},
                 "price_rp_per_kg": 999}
        self.assertEqual(palm.price_value(price), 200)

    def test_price_value_falls_back_through_age_order(self):
        price = {"age_prices_rp_per_kg": {"9": 300, "4": 150}}
        self.assertEqual(palm.price_value(price), 150)

    def test_price_value_falls_back_to_flat_price(self):
        price = {"age_prices_rp_per_kg": {}, "price_rp_per_kg": 3564}
        self.assertEqual(palm.price_value(price), 3564)

    def test_bullets_reads_dash_and_bullet_chars(self):
        self.assertEqual(palm.bullets(FEED),
                         ["Harga TBS Riau naik tipis.",
                          "CPO Bursa Malaysia melemah.",
                          "B50 masih dibahas."])

    def test_bullets_respects_limit(self):
        self.assertEqual(len(palm.bullets(FEED, 2)), 2)

    def test_bullets_empty_when_no_summary(self):
        self.assertEqual(palm.bullets({}), [])


class StoriesAreTheOnlyNewsSource(unittest.TestCase):
    """Berita sawit sekarang datang dari Palm Pulse, bukan RSS/Google News."""

    def test_stories_parsed(self):
        items = palm.stories(FEED)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Judul Palm Pulse")
        self.assertEqual(items[0]["source"], "infosawit")

    def test_stories_respect_limit(self):
        self.assertEqual(len(palm.stories(FEED, 1)), 1)

    def test_story_without_title_dropped(self):
        data = {"stories": [{"source": "x"}, {"title": "   "}]}
        self.assertEqual(palm.stories(data), [])

    def test_story_not_a_dict_dropped(self):
        self.assertEqual(palm.stories({"stories": ["teks", None]}), [])

    def test_duplicate_titles_collapse(self):
        data = {"stories": [{"title": "Sama", "source": "a"},
                            {"title": "  sama ", "source": "b"}]}
        self.assertEqual(len(palm.stories(data)), 1)

    def test_stories_survive_non_dict_feed(self):
        self.assertEqual(palm.stories("rusak"), [])
        self.assertEqual(palm.stories(None), [])

    def test_block_renders_source_suffix(self):
        out = palm.stories_block(FEED)
        self.assertIn("\u2022 Judul Palm Pulse \u2014 infosawit", out)

    def test_block_without_source_has_no_dash(self):
        out = palm.stories_block({"stories": [{"title": "Tanpa sumber"}]})
        self.assertEqual(out, "\u2022 Tanpa sumber")

    def test_block_empty_when_no_stories(self):
        self.assertEqual(palm.stories_block({}), "")
        self.assertEqual(palm.stories_block({"stories": []}), "")

    def test_block_never_prints_none(self):
        data = {"stories": [{"title": "Judul", "source": None, "url": None}]}
        self.assertNotIn("None", palm.stories_block(data))


class MalformedDataCannotCostTheBrief(unittest.TestCase):
    def test_junk_change_drops_direction_only(self):
        line = palm.price_line({"scheme": "Plasma", "price_rp_per_kg": 3640,
                                "change_rp_per_kg": "naik dikit"})
        self.assertIn("Rp3.640/kg", line)
        self.assertNotIn("naik", line)

    def test_price_without_number_is_dropped(self):
        self.assertEqual(palm.price_line({"scheme": "Plasma"}), "")

    def test_non_dict_price_is_dropped(self):
        self.assertEqual(palm.price_line("bukan dict"), "")

    def test_missing_scheme_falls_back(self):
        self.assertIn("TBS:", palm.price_line({"price_rp_per_kg": 3000}))

    def test_never_prints_the_word_none(self):
        messy = {"generated_at": None, "master_summary": None,
                 "tbs_prices": [{"region": None, "scheme": None,
                                 "valid_from": None, "valid_to": None,
                                 "price_rp_per_kg": 3000,
                                 "change_rp_per_kg": None}]}
        block = palm.palm_block(messy, CFG)
        self.assertNotIn("None", block)
        self.assertIn("Rp3.000/kg", block)

    def test_heading_omits_absent_period(self):
        data = {"tbs_prices": [{"region": "riau", "scheme": "Plasma",
                                "price_rp_per_kg": 3000}]}
        block = palm.palm_block(data, CFG)
        self.assertIn("Harga TBS Riau", block)
        self.assertNotIn("s/d", block)

    def test_block_empty_when_nothing_usable(self):
        self.assertEqual(palm.palm_block({}, CFG), "")
        self.assertEqual(palm.palm_block(None, CFG), "")
        self.assertEqual(palm.palm_block({"tbs_prices": "rusak"}, CFG), "")

    def test_all_prices_unusable_drops_section(self):
        data = {"tbs_prices": [{"scheme": "Plasma"}, {"scheme": "Swadaya"}]}
        self.assertEqual(palm.palm_block(data, CFG), "")


class BlockFormatting(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
        self.block = palm.palm_block(FEED, CFG, self.now)

    def test_prices_rendered(self):
        self.assertIn("Plasma: Rp3.640/kg (naik Rp40)", self.block)
        self.assertIn("Swadaya: Rp3.564/kg (turun Rp13)", self.block)

    def test_heading_has_region_and_period(self):
        self.assertIn("Harga TBS Riau (2026-07-22 s/d 2026-07-28)", self.block)

    def test_summary_bullets_included(self):
        self.assertIn("Ringkasan Palm Pulse", self.block)
        self.assertIn("\u2022 Harga TBS Riau naik tipis.", self.block)

    def test_fresh_feed_has_no_stale_note(self):
        self.assertNotIn("belum diperbarui", self.block)

    def test_stale_feed_gets_note(self):
        late = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)
        self.assertIn("belum diperbarui", palm.palm_block(FEED, CFG, late))

    def test_price_block_excludes_stories(self):
        # Berita punya seksinya sendiri; blok harga tidak boleh memuatnya.
        self.assertNotIn("Judul Palm Pulse", self.block)


class MergedMessage(unittest.TestCase):
    def setUp(self):
        self.msg = bb.build_message(CFG, FEED, {}, {}, MARKETS)

    def test_contains_every_section(self):
        for needle in ("BRIEF PAGI", "Harga TBS Riau", "Ringkasan Palm Pulse",
                       "Pasar:", "Berita sawit (Palm Pulse):"):
            self.assertIn(needle, self.msg)

    def test_news_comes_from_palm_pulse(self):
        self.assertIn("Judul Palm Pulse", self.msg)
        self.assertIn("Berita kedua", self.msg)

    def test_tbs_appears_before_markets(self):
        self.assertLess(self.msg.index("Harga TBS"), self.msg.index("Pasar:"))

    def test_markets_appear_before_news(self):
        self.assertLess(self.msg.index("Pasar:"),
                        self.msg.index("Berita sawit"))

    def test_ai_summary_goes_on_top_when_present(self):
        msg = bb.build_message(CFG, FEED, {}, {}, MARKETS,
                               ai_summary="Poin AI.")
        self.assertIn("Ringkasan:", msg)
        self.assertLess(msg.index("Poin AI."), msg.index("Harga TBS"))

    def test_message_survives_missing_palm_data(self):
        msg = bb.build_message(CFG, {}, {}, {}, MARKETS)
        self.assertNotIn("Harga TBS", msg)
        self.assertNotIn("Berita sawit", msg)
        self.assertIn("Pasar:", msg)
        self.assertNotIn("None", msg)

    def test_message_survives_everything_missing(self):
        msg = bb.build_message(CFG, {}, {}, {}, {})
        self.assertIn("data pasar tidak tersedia", msg)
        self.assertNotIn("None", msg)

    def test_footer_links_both_sources(self):
        self.assertIn("https://zurplox.github.io/palm-pulse/", self.msg)
        self.assertIn("https://zurplox.github.io/kebun-sawit-cuaca/", self.msg)


class MalformedMarketsCannotCostTheBrief(unittest.TestCase):
    """Sisi pasar harus setangguh sisi feed: satu field rusak di
    data/markets.json tidak boleh membuat build_brief.py mati."""

    def test_ticker_not_a_dict_is_skipped(self):
        self.assertIn("tidak tersedia", bb.markets_block({"tickers": ["x"]}))

    def test_ticker_pct_as_string_does_not_raise(self):
        out = bb.markets_block({"tickers": [{"label": "A", "last": 10,
                                             "pct": "naik"}]})
        self.assertIn("A: 10.00 (?%)", out)

    def test_ticker_last_as_string_becomes_dash(self):
        out = bb.markets_block({"tickers": [{"label": "A", "last": "n/a",
                                             "pct": 1.5}]})
        self.assertIn("A: - (+1.5%)", out)

    def test_numeric_string_pct_is_rendered_cleanly(self):
        out = bb.markets_block({"tickers": [{"label": "A", "last": 1,
                                             "pct": "-2.50"}]})
        self.assertIn("\u25bc A: 1 (-2.5%)", out)

    def test_markets_not_a_dict_is_survivable(self):
        self.assertIn("tidak tersedia", bb.markets_block("rusak"))

    def test_fx_without_pair_is_skipped(self):
        self.assertIn("tidak tersedia",
                      bb.markets_block({"fx": [{"rate": 5}]}))

    def test_percent_formatting_matches_previous_output(self):
        out = bb.markets_block({"tickers": [
            {"label": "VOO", "last": 679.31, "pct": -0.43},
            {"label": "QQQ", "last": 682.12, "pct": -2.0},
            {"label": "VEU", "last": 82.01, "pct": 0.94}]})
        # Persis seperti keluaran lama: -2.0 tetap "-2.0%", bukan "-2%".
        self.assertIn("\u25bc VOO: 679.31 (-0.43%)", out)
        self.assertIn("\u25bc QQQ: 682.12 (-2.0%)", out)
        self.assertIn("\u25b2 VEU: 82.01 (+0.94%)", out)

    def test_flat_pct_zero_shows_arrow_right(self):
        out = bb.markets_block({"tickers": [{"label": "A", "last": 1,
                                             "pct": 0}]})
        self.assertIn("\u2192 A: 1 (0%)", out)

    def test_fmt_num_thresholds_unchanged(self):
        # Perilaku angka lama dikunci: <10 dipangkas, >=10 dua desimal,
        # >=1000 pakai titik ribuan.
        self.assertEqual(bb.fmt_num(9.5), "9.5")
        self.assertEqual(bb.fmt_num(10), "10.00")
        self.assertEqual(bb.fmt_num(16290.5), "16.290")
        self.assertEqual(bb.fmt_num(None), "-")
        self.assertEqual(bb.fmt_num("n/a"), "-")

    def test_whole_message_survives_every_kind_of_junk(self):
        msg = bb.build_message(CFG, "rusak", "rusak", "rusak",
                               {"tickers": ["x"], "fx": "y"})
        self.assertNotIn("None", msg)
        self.assertIn("BRIEF PAGI", msg)


class FeedOfTheWrongTypeCannotBreakTheBuild(unittest.TestCase):
    """Regresi: data/*.json milik repo lain bisa saja berubah bentuk. Kalau
    sebuah berkas ternyata list atau string, build_brief.py harus tetap
    menerbitkan brief, bukan mati dan membuat workflow merah."""

    def test_as_dict_passes_objects_through(self):
        self.assertEqual(bb.as_dict({"a": 1}), {"a": 1})

    def test_as_dict_neutralises_wrong_types(self):
        for junk in (["list"], "string", 3, None, True):
            self.assertEqual(bb.as_dict(junk), {})

    def test_message_still_builds_from_neutralised_feeds(self):
        msg = bb.build_message(CFG, bb.as_dict(["rusak"]), bb.as_dict("rusak"),
                               bb.as_dict(None), MARKETS)
        self.assertIn("BRIEF PAGI", msg)
        self.assertIn("Pasar:", msg)
        self.assertNotIn("None", msg)


if __name__ == "__main__":
    unittest.main()

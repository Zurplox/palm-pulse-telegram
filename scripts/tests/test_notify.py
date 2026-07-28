#!/usr/bin/env python3
"""Tes offline untuk scripts/notify.py. Tanpa jaringan.

Jalankan: python -m unittest discover -s scripts/tests
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import notify as nt  # noqa: E402

ENV_KEYS = ["WA_PHONE", "WA_APIKEY", "TG_TOKEN", "TG_CHAT_ID",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "FORCE_SEND"]


class EnvSafe(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class Helpers(EnvSafe):
    def test_setting_blank_falls_back(self):
        os.environ["TG_TOKEN"] = ""
        self.assertEqual(nt.setting("TG_TOKEN", "fallback"), "fallback")

    def test_setting_strips(self):
        os.environ["TG_CHAT_ID"] = "  12345  "
        self.assertEqual(nt.setting("TG_CHAT_ID"), "12345")

    def test_scrub_hides_token_in_url(self):
        msg = "HTTP Error 401: https://api.telegram.org/bot8123456789:AAF3xSecretValue/sendMessage"
        out = nt.scrub(msg)
        self.assertNotIn("AAF3xSecretValue", out)
        self.assertIn("bot<TOKEN>", out)

    def test_scrub_hides_bare_token(self):
        out = nt.scrub("token 8123456789:AAF3xSecretValueThatIsLongEnough00 bocor")
        self.assertNotIn("AAF3xSecretValueThatIsLongEnough00", out)

    def test_plain_strips_whatsapp_bold(self):
        self.assertEqual(nt.plain("\U0001F4F0 *BRIEF PAGI* \u2014 28 Jul"),
                         "\U0001F4F0 BRIEF PAGI \u2014 28 Jul")

    def test_plain_keeps_lone_asterisk(self):
        self.assertEqual(nt.plain("harga naik 5* lipat"), "harga naik 5* lipat")


class Chunking(EnvSafe):
    def test_short_message_is_one_chunk(self):
        self.assertEqual(nt.split_chunks("halo\ndunia", 3800), ["halo\ndunia"])

    def test_splits_on_newline_boundary(self):
        text = "\n".join("baris %d" % i for i in range(500))
        chunks = nt.split_chunks(text, 200)
        self.assertTrue(len(chunks) > 1)
        for c in chunks:
            self.assertLessEqual(len(c), 200)
        self.assertEqual("\n".join(chunks), text)

    def test_url_never_cut_in_half(self):
        url = "https://www.infosawit.com/berita/harga-cpo-hari-ini-2026"
        text = "\n".join(["padding" * 20] * 5 + [url])
        chunks = nt.split_chunks(text, 200)
        self.assertTrue(any(url in c for c in chunks))

    def test_single_overlong_line_is_hard_cut(self):
        chunks = nt.split_chunks("x" * 500, 100)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertEqual("".join(chunks), "x" * 500)

    def test_real_brief_fits_telegram(self):
        text = "\n".join(["\u2022 judul berita panjang sekali " * 6] * 40)
        for c in nt.split_chunks(nt.plain(text), nt.TG_LIMIT):
            self.assertLess(len(c) + 20, 4096)


class TelegramDelivery(EnvSafe):
    def setUp(self):
        super().setUp()
        self.calls = []
        self._post = nt.tg_post
        self._sleep = nt.time.sleep
        nt.time.sleep = lambda s: None

    def tearDown(self):
        nt.tg_post = self._post
        nt.time.sleep = self._sleep
        super().tearDown()

    def test_sends_plain_text_without_asterisks(self):
        nt.tg_post = lambda t, c, x: self.calls.append(x) or 200
        nt.tg_send("tok", "1", "*TEBAL* isi")
        self.assertEqual(self.calls, ["TEBAL isi"])

    def test_long_message_sent_in_parts_with_counter(self):
        nt.tg_post = lambda t, c, x: self.calls.append(x) or 200
        parts = nt.tg_send("tok", "1", "\n".join("baris %d" % i
                                                 for i in range(3000)))
        self.assertGreater(parts, 1)
        self.assertIn("(1/%d)" % parts, self.calls[0])

    def test_429_is_retried_once(self):
        state = {"n": 0}

        def flaky(t, c, x):
            state["n"] += 1
            if state["n"] == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many", None, None)
            return 200

        nt.tg_post = flaky
        nt.tg_send("tok", "1", "halo", pause=0)
        self.assertEqual(state["n"], 2)

    def test_400_is_not_retried(self):
        state = {"n": 0}

        def bad(t, c, x):
            state["n"] += 1
            raise urllib.error.HTTPError("u", 400, "Bad Request", None, None)

        nt.tg_post = bad
        with self.assertRaises(RuntimeError):
            nt.tg_send("tok", "1", "halo", pause=0)
        self.assertEqual(state["n"], 1)

    def test_error_message_carries_no_token(self):
        def leak(t, c, x):
            raise Exception("failed https://api.telegram.org/bot999999:SECRETSECRETSECRETSECRET/sendMessage")

        nt.tg_post = leak
        with self.assertRaises(RuntimeError) as ctx:
            nt.tg_send("tok", "1", "halo", pause=0)
        self.assertNotIn("SECRETSECRETSECRETSECRET", str(ctx.exception))


class DuplicateGuard(EnvSafe):
    def test_per_channel_state(self):
        today = date(2026, 7, 28)
        st = {"whatsapp": "2026-07-28T07:00"}
        self.assertTrue(nt.already_sent_today(st, "whatsapp", today))
        self.assertFalse(nt.already_sent_today(st, "telegram", today))

    def test_legacy_state_counts_for_whatsapp_only(self):
        today = date(2026, 7, 28)
        st = {"date": "2026-07-28T07:00"}
        self.assertTrue(nt.already_sent_today(st, "whatsapp", today))
        self.assertFalse(nt.already_sent_today(st, "telegram", today))

    def test_yesterday_does_not_block(self):
        st = {"telegram": "2026-07-27T07:00"}
        self.assertFalse(nt.already_sent_today(st, "telegram",
                                               date(2026, 7, 28)))

    def test_corrupt_state_does_not_block(self):
        st = {"telegram": "bukan-tanggal"}
        self.assertFalse(nt.already_sent_today(st, "telegram",
                                               date(2026, 7, 28)))

    def test_remember_survives_unwritable_path(self):
        old = nt.LAST
        nt.LAST = "/proc/definitely/not/writable/last_sent.json"
        try:
            out = nt.remember({}, "telegram", datetime.now(timezone.utc))
            self.assertIn("telegram", out)
        finally:
            nt.LAST = old

    def test_remember_writes_both_keys(self):
        old = nt.LAST
        tmp = tempfile.mkdtemp()
        nt.LAST = os.path.join(tmp, "data", "last_sent.json")
        try:
            now = datetime(2026, 7, 28, 7, 5, tzinfo=timezone.utc)
            nt.remember({}, "telegram", now)
            with open(nt.LAST, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertIn("telegram", saved)
            self.assertIn("date", saved)
        finally:
            nt.LAST = old


class MainNeverFails(EnvSafe):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "data"))
        self._root, self._last = nt.ROOT, nt.LAST
        nt.ROOT = self.tmp
        nt.LAST = os.path.join(self.tmp, "data", "last_sent.json")
        self._wa, self._tg = nt.wa_send, nt.tg_send

    def tearDown(self):
        nt.ROOT, nt.LAST = self._root, self._last
        nt.wa_send, nt.tg_send = self._wa, self._tg
        super().tearDown()

    def write_msg(self, text="*BRIEF PAGI* \u2014 28 Jul 2026\nisi brief"):
        with open(os.path.join(self.tmp, "data", "brief_message.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text)

    def test_no_message_file_exits_quietly(self):
        nt.main()

    def test_no_credentials_makes_no_call(self):
        self.write_msg()
        nt.tg_send = lambda *a, **k: self.fail("tidak boleh kirim")
        nt.wa_send = lambda *a, **k: self.fail("tidak boleh kirim")
        nt.main()

    def test_telegram_alias_secret_names_work(self):
        self.write_msg()
        seen = {}
        nt.tg_send = lambda t, c, m: seen.update(token=t, chat=c) or 1
        os.environ["TELEGRAM_BOT_TOKEN"] = "tok"
        os.environ["TELEGRAM_CHAT_ID"] = "555"
        nt.main()
        self.assertEqual(seen, {"token": "tok", "chat": "555"})

    def test_telegram_failure_does_not_record_state(self):
        self.write_msg()

        def boom(*a, **k):
            raise RuntimeError("Telegram menolak pesan (HTTP 400)")

        nt.tg_send = boom
        os.environ["TG_TOKEN"] = "tok"
        os.environ["TG_CHAT_ID"] = "1"
        nt.main()
        self.assertFalse(os.path.exists(nt.LAST))

    def test_whatsapp_success_does_not_block_telegram(self):
        self.write_msg()
        hits = []
        nt.wa_send = lambda *a: hits.append("wa") or 1
        nt.tg_send = lambda *a: hits.append("tg") or 1
        os.environ.update(WA_PHONE="628", WA_APIKEY="k", TG_TOKEN="t",
                          TG_CHAT_ID="1")
        nt.main()
        self.assertEqual(sorted(hits), ["tg", "wa"])

    def test_second_run_same_day_skips_telegram(self):
        self.write_msg()
        hits = []
        nt.tg_send = lambda *a: hits.append("tg") or 1
        os.environ.update(TG_TOKEN="t", TG_CHAT_ID="1")
        nt.main()
        nt.main()
        self.assertEqual(hits, ["tg"])

    def test_force_send_overrides_guard(self):
        self.write_msg()
        hits = []
        nt.tg_send = lambda *a: hits.append("tg") or 1
        os.environ.update(TG_TOKEN="t", TG_CHAT_ID="1")
        nt.main()
        os.environ["FORCE_SEND"] = "1"
        nt.main()
        self.assertEqual(hits, ["tg", "tg"])

    def test_partial_telegram_credentials_skipped(self):
        self.write_msg()
        nt.tg_send = lambda *a: self.fail("tidak boleh kirim")
        os.environ["TG_TOKEN"] = "t"
        nt.main()

    def test_empty_message_sends_nothing(self):
        self.write_msg("   ")
        nt.tg_send = lambda *a: self.fail("tidak boleh kirim")
        os.environ.update(TG_TOKEN="t", TG_CHAT_ID="1")
        nt.main()


if __name__ == "__main__":
    unittest.main()

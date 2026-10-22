#!/usr/bin/env python3
"""Tes offline fallback model Gemini di build_brief. Tanpa jaringan.

Jalankan: python -m unittest discover -s scripts/tests
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import build_brief as bb  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self._payload


def reply(*parts):
    return {"candidates": [{"content": {"parts": list(parts)}}]}


class GeminiFallback(unittest.TestCase):
    def test_first_model_wins(self):
        calls = []

        def fake_urlopen(req, timeout=0):
            calls.append(req.full_url)
            return FakeResponse(reply({"text": "ok"}))

        with mock.patch.object(bb.urllib.request, "urlopen", fake_urlopen):
            out = bb.gemini_summary("data", "KEY")

        self.assertEqual(out, "ok")
        self.assertEqual(len(calls), 1)
        self.assertIn(bb.GEMINI_MODELS[0], calls[0])

    def test_falls_through_and_skips_thought_parts(self):
        calls = []

        def fake_urlopen(req, timeout=0):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise RuntimeError("404 model not found")
            return FakeResponse(reply({"text": "pikiran", "thought": True},
                                      {"text": "jawaban"}))

        with mock.patch.object(bb.urllib.request, "urlopen", fake_urlopen):
            out = bb.gemini_summary("data", "KEY")

        self.assertEqual(out, "jawaban")
        self.assertIn(bb.GEMINI_MODELS[0], calls[0])
        self.assertIn(bb.GEMINI_MODELS[1], calls[1])

    def test_all_models_fail(self):
        def fake_urlopen(req, timeout=0):
            raise RuntimeError("down")

        with mock.patch.object(bb.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError):
                bb.gemini_summary("data", "KEY")


if __name__ == "__main__":
    unittest.main()

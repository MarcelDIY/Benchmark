#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schnelle Unit-Tests ohne Ollama/Netzwerk. Lauf: python -m unittest -v aus dem Repo.

Testet die deterministische Logik von bench.py sowie die reinen GUI-Helfer.
Die GUI-Tests werden uebersprungen, wenn PySide6 nicht installiert ist.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench


class TestBenchLogik(unittest.TestCase):
    def test_agg_leer(self):
        self.assertEqual(bench.agg([]), (None, None))

    def test_agg_median(self):
        med, p95 = bench.agg([1, 2, 3, 4, 5])
        self.assertEqual(med, 3)
        self.assertEqual(p95, 5)

    def test_agg_ignoriert_none(self):
        med, _ = bench.agg([None, 2, 4, None])
        self.assertEqual(med, 3)

    def test_f(self):
        self.assertEqual(bench._f(None), "")
        self.assertEqual(bench._f(1.23456, 1), 1.2)
        self.assertEqual(bench._f(1.23456, 0), 1)

    def test_norm_umlaute(self):
        self.assertEqual(bench._norm("MÄRZ"), bench._norm("maerz"))
        self.assertEqual(bench._norm("Größe"), "groesse")

    def test_quality_check_keys_ok(self):
        task = {"check_keys": ["a", "b"]}
        self.assertTrue(bench.quality_check(task, 'Text {"a":1,"b":2} Ende'))

    def test_quality_check_keys_fail(self):
        task = {"check_keys": ["a", "b"]}
        self.assertFalse(bench.quality_check(task, '{"a":1}'))
        self.assertFalse(bench.quality_check(task, "kein json"))

    def test_quality_check_contains_umlauttolerant(self):
        task = {"expect_contains": "25. März"}
        self.assertTrue(bench.quality_check(task, "Vorlage bis zum 25. Maerz."))

    def test_quality_check_none(self):
        self.assertIsNone(bench.quality_check({}, "irgendwas"))

    def test_run_once_signatur_hat_should_cancel(self):
        # GUI-Abbruch haengt an diesem optionalen Parameter.
        import inspect
        params = inspect.signature(bench.run_once).parameters
        self.assertIn("should_cancel", params)
        self.assertIsNone(params["should_cancel"].default)


class TestGuiHelfer(unittest.TestCase):
    def setUp(self):
        try:
            import benchmark_gui
        except Exception as e:  # PySide6 nicht da -> ueberspringen
            self.skipTest(f"PySide6/GUI nicht importierbar: {e}")
        self.G = benchmark_gui

    def test_normalize_host(self):
        self.assertEqual(self.G.normalize_host("localhost:11434"), "http://localhost:11434")
        self.assertEqual(self.G.normalize_host(""), "http://localhost:11434")
        self.assertEqual(self.G.normalize_host("http://x:1"), "http://x:1")
        self.assertEqual(self.G.normalize_host("  192.168.2.12:11434 "),
                         "http://192.168.2.12:11434")

    def test_safe_label(self):
        self.assertEqual(self.G.safe_label("mac m4:pro/2"), "mac_m4_pro_2")
        self.assertEqual(self.G.safe_label(""), "rechner")
        self.assertEqual(self.G.safe_label(None), "rechner")

    def test_table_cols_decken_md_keys(self):
        # Die sichtbaren Spalten muessen Schluessel der Summary-Zeile sein.
        keys = {k for k, _ in self.G.TABLE_COLS}
        for need in ("task", "decode_toks_med", "quality"):
            self.assertIn(need, keys)


if __name__ == "__main__":
    unittest.main()

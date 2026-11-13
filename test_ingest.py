#!/usr/bin/env python3
"""Tests for schema-backed spectrum ingestion."""

import json
import sqlite3
import unittest

from compass import score_triplet
from ingest import ingest, initialize_database


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        initialize_database(self.db)
        self.addCleanup(self.db.close)

    def test_doi_only(self):
        result = ingest("10.1234/example", self.db)
        self.assertEqual(result["score"], None)
        self.assertEqual(result["traps"], [])
        self.assertIsNone(result["morphology_id"])
        row = self.db.execute(
            "SELECT paper_doi, sample_type, condition, freq_unit, raw_frequencies "
            "FROM spectra WHERE spectrum_id = ?", (result["spectrum_id"],)).fetchone()
        self.assertEqual(row, ("10.1234/example", "unknown", "unknown", "THz", "[]"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM scores").fetchone()[0], 0)

    def test_raw_triplet_and_line_metadata(self):
        result = ingest([103, 71, 87], self.db, metadata={
            "sample_type": "tissue", "live_or_dried": "live", "temperature_k": 300,
            "intensity": [3, 1, 2], "claimed_assignment": ["a", "b", "c"],
            "kappa_sensitivity_note": "not tested",
        })
        expected = score_triplet(71, 87, 103)
        self.assertEqual(result["score"]["score"], expected["score"])
        self.assertEqual(result["score"]["gaps_thz"], expected["gaps_thz"])
        self.assertEqual(self.db.execute(
            "SELECT frequency_thz, intensity, author_assignment FROM lines ORDER BY line_id"
        ).fetchall(), [(103, 3, "a"), (71, 1, "b"), (87, 2, "c")])
        row = self.db.execute(
            "SELECT compass_score, cross_ratio, mean_error_thz, gaps_thz, "
            "rydberg_denominators, trap_flags, kappa_sensitivity FROM scores"
        ).fetchone()
        self.assertEqual(row[:3], (expected["score"], expected["cross_ratio"],
                                   expected["mean_error_thz"]))
        self.assertEqual(json.loads(row[3]), expected["gaps_thz"])
        self.assertEqual(json.loads(row[4]), expected["rydberg_denominators"])
        self.assertEqual(json.loads(row[5]), result["score"]["trap_flags"])
        self.assertEqual(row[6], "not tested")
        self.assertEqual(json.loads(self.db.execute(
            "SELECT raw_frequencies FROM spectra").fetchone()[0]), [103, 71, 87])

    def test_frequency_units(self):
        for unit, values in (("MHz", [71000000, 87000000, 103000000]),
                             ("GHz", [71000, 87000, 103000]),
                             ("Hz", [71000000000000, 87000000000000, 103000000000000])):
            with self.subTest(unit=unit):
                result = ingest(values, self.db, frequency_unit=unit)
                lines = self.db.execute(
                    "SELECT frequency_thz FROM lines WHERE spectrum_id = ? ORDER BY line_id",
                    (result["spectrum_id"],)).fetchall()
                for actual, expected in zip(lines, [71, 87, 103]):
                    self.assertAlmostEqual(actual[0], expected)
                self.assertEqual(self.db.execute(
                    "SELECT freq_unit FROM spectra WHERE spectrum_id = ?",
                    (result["spectrum_id"],)).fetchone()[0], "THz")

    def test_band_join_and_partial_result(self):
        result = ingest([69, 71, 72.1], self.db)
        self.assertEqual(len(result["traps"]), 2)
        self.assertTrue(all("CO2_asymmetric_stretch" in flag for flag in result["traps"]))
        self.assertTrue(all("Fudan" not in flag for flag in result["traps"]))
        short = ingest([70.5, 120], self.db)
        self.assertIsNone(short["score"])
        self.assertEqual(len(short["traps"]), 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM lines WHERE spectrum_id = ?", (short["spectrum_id"],)
        ).fetchone()[0], 2)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM scores WHERE spectrum_id = ?", (short["spectrum_id"],)
        ).fetchone()[0], 0)

    def test_morphology_attachment(self):
        result = ingest([80], self.db, metadata={
            "crista_density_per_micron": 4.2, "lamellar_vs_tubular": "tubular",
            "lumen_width_nm": 25,
        })
        self.assertEqual(self.db.execute(
            "SELECT spectrum_id, crista_density_per_micron, morphology, lumen_width_nm "
            "FROM morphologies WHERE morph_id = ?", (result["morphology_id"],)
        ).fetchone(), (result["spectrum_id"], 4.2, "tubular", 25))

    def test_band_matching_uses_database_tolerance(self):
        self.db.execute("UPDATE bands SET tolerance_thz = 0.1 "
                        "WHERE name = 'CO2_asymmetric_stretch'")
        result = ingest([70.5], self.db)
        self.assertEqual(result["traps"], [])
        result = ingest([70.05], self.db)
        self.assertIn("CO2_asymmetric_stretch", result["traps"][0])

    def test_multiple_triplets(self):
        result = ingest([120, 71, 87, 103], self.db)
        scores = self.db.execute(
            "SELECT compass_score FROM scores WHERE spectrum_id = ?", (result["spectrum_id"],)
        ).fetchall()
        self.assertEqual(len(scores), 4)
        self.assertEqual(result["score"]["score"], max(row[0] for row in scores))

    def test_invalid_inputs_do_not_write(self):
        cases = [
            ([0, 1, 2], {}),
            ([float("nan")], {}),
            ([1], {"frequency_unit": "bogus"}),
            ([1, 2], {"metadata": {"intensity": [1]}}),
            ([1], {"metadata": {"lamellar_vs_tubular": "other"}}),
            ([1e-300, 1e100, 1e200], {}),
        ]
        for source, kwargs in cases:
            with self.subTest(source=source, kwargs=kwargs), self.assertRaises(ValueError):
                ingest(source, self.db, **kwargs)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM spectra").fetchone()[0], 0)

    def test_write_failure_rolls_back_spectrum(self):
        self.db.execute("CREATE TRIGGER fail_line BEFORE INSERT ON lines "
                        "BEGIN SELECT RAISE(ABORT, 'line rejected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            ingest([71, 87, 103], self.db)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM spectra").fetchone()[0], 0)

    def test_outer_transaction_is_preserved(self):
        self.db.execute("BEGIN")
        ingest([70], self.db)
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM spectra").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

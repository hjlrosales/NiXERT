"""Tests for the validated DAT parser."""

from __future__ import annotations

import unittest

from nix_ert.data.dat_import import DATParseError, parse_dat, preview_dat


class DATImportTests(unittest.TestCase):
    def test_canonical_rows_and_electrodes(self) -> None:
        dataset = parse_dat("""3
5.0
3
0
1 2 3 4 100.0
2 3 4 5 200.0
1 3 4 6 0.0
""", "line.dat")
        self.assertEqual(dataset.source_name, "line.dat")
        self.assertEqual(dataset.array_type, "Dipole-Dipole")
        self.assertEqual(dataset.data_count, 3)
        self.assertEqual(len(dataset.electrodes), 6)
        self.assertEqual(dataset.electrodes[0].x, 0.0)
        self.assertEqual(dataset.measurements[1].a, 2)
        self.assertEqual(dataset.invalid_measurement_count, 1)

    def test_indexed_rows_and_optional_fields_are_preserved(self) -> None:
        dataset = parse_dat("""1
2
Wenner
0
1 1 2 3 4 10 0.5 2.0 3.0
""")
        measurement = dataset.measurements[0]
        self.assertEqual(measurement.measurement_index, 1)
        self.assertEqual((measurement.a, measurement.b, measurement.m, measurement.n), (1, 2, 3, 4))
        self.assertEqual(measurement.resistance, 0.5)
        self.assertEqual(measurement.current, 2.0)
        self.assertEqual(measurement.voltage, 3.0)

    def test_ambiguous_optional_width_requires_explicit_row_format(self) -> None:
        text = """1
2
Wenner
0
1 2 3 4 10 0.5
"""
        with self.assertRaisesRegex(DATParseError, "ambiguous"):
            parse_dat(text)
        dataset = parse_dat(text, row_format="canonical")
        self.assertEqual((dataset.measurements[0].a, dataset.measurements[0].resistance), (1, 0.5))

        dataset = parse_dat("""1
10
1
2
0 100
10 101.5
1 2 3 4 50
""")
        self.assertEqual(dataset.topography, ((0.0, 100.0), (10.0, 101.5)))

    def test_count_mismatch_and_unknown_array_are_rejected(self) -> None:
        with self.assertRaisesRegex(DATParseError, "Expected 2 measurement rows"):
            parse_dat("2\n1\n1\n0\n1 2 3 4 10\n")
        with self.assertRaisesRegex(DATParseError, "unsupported array type"):
            parse_dat("0\n1\n99\n")

    def test_preview_reports_file_facts(self) -> None:
        preview = preview_dat("2\n1\n5\n0\n1 2 3 4 10\n2 3 4 5 -2\n", "x.dat")
        self.assertEqual((preview.parsed_count, preview.electrode_count), (2, 5))
        self.assertEqual(preview.invalid_measurement_count, 1)
        self.assertTrue(preview.warnings)


if __name__ == "__main__":
    unittest.main()

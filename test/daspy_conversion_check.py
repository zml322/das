"""End-to-end checks for the project BIN to DASPy conversion helper."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import daspy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.daspy_conversion import (
    FORMAT_EXTENSIONS,
    build_section_from_bin,
    convert_bin_to_daspy,
    normalize_output_path,
    read_bin_metadata,
)


SAMPLE_BIN = PROJECT_ROOT / "test" / "ch1_2026-08-26-16-54-19_2_30720_520_1000.bin"


@unittest.skipUnless(SAMPLE_BIN.is_file(), "real BIN sample is unavailable")
class DASPyConversionTests(unittest.TestCase):
    def test_header_metadata_and_manual_section_values(self) -> None:
        metadata = read_bin_metadata(SAMPLE_BIN)
        self.assertEqual((metadata.channel_count, metadata.sampling_times), (520, 30720))
        self.assertEqual(metadata.sampling_rate, 1000.0)
        self.assertEqual(metadata.start_time.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-26 16:54:19")

        section, _metadata = build_section_from_bin(
            SAMPLE_BIN,
            channel_spacing=4.0,
            sampling_rate=800.0,
            start_channel=3,
            start_distance=12.5,
            gauge_length=10.0,
            data_type="strain rate",
            scale=2.0,
        )
        self.assertEqual(section.data.shape, (520, 30720))
        self.assertEqual((section.dx, section.fs), (4.0, 800.0))
        self.assertEqual((section.start_channel, section.start_distance), (3, 12.5))
        self.assertEqual((section.gauge_length, section.data_type, section.scale), (10.0, "strain rate", 2.0))

    def test_verified_formats_round_trip_without_changing_source(self) -> None:
        before = (SAMPLE_BIN.stat().st_size, SAMPLE_BIN.stat().st_mtime_ns)
        with tempfile.TemporaryDirectory(prefix="daspy-bin-conversion-test-") as folder:
            root = Path(folder)
            for output_format in ("pkl", "h5", "sgy"):
                output, _metadata = convert_bin_to_daspy(
                    SAMPLE_BIN,
                    root / f"converted.{output_format}",
                    output_format,
                    channel_spacing=4.0,
                    gauge_length=10.0,
                    data_type="strain rate",
                )
                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 0)
                reloaded = daspy.read(output)
                self.assertEqual(reloaded.data.shape, (520, 30720))
                self.assertEqual(reloaded.fs, 1000.0)
                if output_format in {"pkl", "h5"}:
                    self.assertEqual(reloaded.dx, 4.0)
                else:
                    self.assertIsNone(reloaded.dx)
        self.assertEqual(before, (SAMPLE_BIN.stat().st_size, SAMPLE_BIN.stat().st_mtime_ns))

    def test_output_extension_is_controlled_by_selected_format(self) -> None:
        self.assertEqual(normalize_output_path("result.any", "pkl").suffix, ".pkl")
        self.assertEqual(normalize_output_path("result.any", "h5").suffix, ".h5")
        self.assertEqual(normalize_output_path("result.any", "sgy").suffix, ".sgy")
        self.assertEqual(FORMAT_EXTENSIONS, {"pkl": ".pkl", "h5": ".h5", "sgy": ".sgy"})


if __name__ == "__main__":
    unittest.main()

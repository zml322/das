"""Focused checks for per-channel MAD normalization."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.das_filter import apply_das_filter


class MadNormalizationTests(unittest.TestCase):
    def test_channels_are_normalized_independently(self) -> None:
        data = np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 40.0],
                [-30.0, -3.0, -2.0, -1.0, 0.0],
            ],
            dtype=np.float32,
        )

        result = apply_das_filter(data, 1000.0, "mad_normalize", {})

        values = data.astype(np.float64)
        medians = np.median(values, axis=1, keepdims=True)
        mad = np.median(np.abs(values - medians), axis=1, keepdims=True)
        expected = ((values - medians) / (1.4826 * mad)).astype(np.float32)
        np.testing.assert_allclose(result, expected, rtol=1e-6, atol=1e-6)
        self.assertEqual(result.shape, data.shape)
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(result)))

    def test_constant_channel_becomes_zero(self) -> None:
        data = np.array(
            [
                [7.0, 7.0, 7.0, 7.0],
                [1.0, 2.0, 3.0, 4.0],
            ],
            dtype=np.float32,
        )

        result = apply_das_filter(data, 1000.0, "mad_normalize", {})

        np.testing.assert_array_equal(result[0], np.zeros(4, dtype=np.float32))
        self.assertTrue(np.all(np.isfinite(result)))

    def test_selected_rectangle_leaves_other_data_untouched(self) -> None:
        working_data = np.arange(30, dtype=np.float32).reshape(3, 10)
        before = working_data.copy()
        channel_slice = slice(1, 3)
        sample_slice = slice(2, 8)

        working_data[channel_slice, sample_slice] = apply_das_filter(
            working_data[channel_slice, sample_slice],
            1000.0,
            "mad_normalize",
            {},
        )

        changed = np.zeros(before.shape, dtype=bool)
        changed[channel_slice, sample_slice] = True
        np.testing.assert_array_equal(working_data[~changed], before[~changed])
        self.assertTrue(np.all(np.isfinite(working_data)))


if __name__ == "__main__":
    unittest.main()

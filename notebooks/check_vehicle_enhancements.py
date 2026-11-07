"""Physical direction, real symmetry, envelope centering and empty-input checks."""

import numpy as np
from vehicle_enhancements import directional_fk, hilbert_envelope, scale_feature_mad


def main():
    fs, dx = 40.0, 4.0
    rows, samples = 128, 4800
    t = np.arange(samples) / fs
    x = np.arange(rows)[:, None] * dx
    # Opposite travelling sinusoids, with distinct temporal frequencies.
    increasing = np.cos(2 * np.pi * (0.8 * t - x / 64))
    decreasing = 0.7 * np.cos(2 * np.pi * (1.2 * t + x / 80))
    options = dict(padding_seconds=0, padding_channels=0, taper_fraction=0, transition_bins=1)
    # Exact space/time DFT bins make direction leakage measurable without edges.
    target = np.cos(2 * np.pi * (0.8 * t - 8 * x / (rows * dx)))
    opposite = np.cos(2 * np.pi * (1.2 * t + 12 * x / (rows * dx)))
    pos, info = directional_fk(target + opposite, fs, dx, direction='increasing', **options)
    neg, _ = directional_fk(target + opposite, fs, dx, direction='decreasing', **options)
    assert np.sqrt(np.mean((pos - target) ** 2)) < 2e-5
    assert np.sqrt(np.mean((neg - opposite) ** 2)) < 2e-5
    assert info['imaginary_fraction'] < 2e-5
    # Repeat with odd sizes, real padding, and smooth boundaries (normal path).
    original = (increasing + decreasing)[:127, :4701].astype(np.float32)
    saved = original.copy()
    for direction in ('increasing', 'decreasing'):
        filtered, diagnostics = directional_fk(original, fs, dx, direction=direction)
        assert filtered.shape == original.shape and np.isfinite(filtered).all()
        assert diagnostics['imaginary_fraction'] < 2e-5
    np.testing.assert_array_equal(original, saved)

    # Two close envelopes must remain two events; no one-peak-per-car assertion.
    amplitude = np.exp(-0.5 * ((t - 45) / 1.4) ** 2)
    amplitude += 0.8 * np.exp(-0.5 * ((t - 51) / 1.4) ** 2)
    carrier = amplitude * np.cos(2 * np.pi * 4 * t)
    envelope = hilbert_envelope(np.tile(carrier, (2, 1)), fs, smoothing_seconds=0.25)
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(envelope[0], prominence=0.2)
    assert len(peaks) == 2
    np.testing.assert_allclose(t[peaks], [45, 51], atol=1 / fs)
    assert envelope.min() >= 0
    zero = np.zeros((4, 101), dtype=np.float32)
    for direction in ('increasing', 'decreasing'):
        filtered, diagnostics = directional_fk(zero, fs, dx, direction=direction)
        assert not filtered.any() and diagnostics['passed_spectral_energy_fraction'] == 0
    scaled, _ = scale_feature_mad(hilbert_envelope(zero, fs))
    assert not scaled.any()
    for bad in (np.ones(5), np.full((2, 5), np.nan)):
        try:
            directional_fk(bad, fs, dx, direction='increasing')
        except ValueError:
            pass
        else:
            raise AssertionError('invalid input accepted')
    print('PASS: FFT direction signs, conjugate symmetry, odd/even sizes, no mutation,')
    print('      two distinct envelopes without sample shifts, zero input and validation')


if __name__ == '__main__':
    main()

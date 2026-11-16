# das_veh source provenance and adaptation

Source: https://github.com/syyuan93/das_veh

Pinned commit: `b1831d2d2a5636ec416095f9647a33881afaeed1` (2023-11-03).

Vendored files:

- `apis/tracking.py` → `tracking.py`
- `modules/car_tracking_utils.py` → `car_tracking_utils.py`

License: MIT, Copyright (c) 2023 Siyuan Yuan. Full notice is in
`licenses/das_veh-LICENSE.txt`. Upstream notes that Kalman code is based on
https://github.com/jingxiaoliu/TelecomTM; that attribution is preserved.

## Changes to upstream source

- Remove the author's absolute `sys.path`; use a package-relative import.
- Remove an unused ObsPy import. No additional runtime dependencies.
- Clamp the seed section at the last channel; allow empty results and empty
  interpolation rows. Avoid computing plot percentiles when plots are disabled.
- Convert single-element NumPy arrays to scalars for NumPy compatibility;
  fix the tuple indexing in the nearest/positive peak selection.
- Fix the returned channel count when it is not divisible by the spatial step.
- Optional adapter arguments: cached peak locations, cancellation/progress,
  spatial step, observation covariance, association window, nearest residual,
  consecutive missing-channel limit, two-point slope initialization, and raw
  observed states before the upstream extrapolation/cleanup.
- Keep the original transition matrix A, process matrix Q, Kalman gain and
  covariance update equations. Adapter noise variances scale by `(fs/50)^2`
  because the upstream state uses temporal sample indices, not seconds.
- For long uniformly sampled time axes, compute the original Gaussian seed
  likelihood by FFT convolution at **every original sample**, truncating the
  Gaussian at eight standard deviations and suppressing numerical round-off
  seed peaks. The direct Gaussian implementation remains for shorter inputs.

`utils/classes/das_veh_tracking.py` is the separate application adapter:

- BIN windows and filter padding at the actual acquisition rate; no temporal
  resampling/decimation or spatial interpolation.
- Upstream order-10 temporal Butterworth bandpass, stable float64 SOS, followed
  by per-channel MAD normalization so prominence controls are comparable.
- Forward/reversed original-channel views and separate positive/negative peaks.
- Return measured sample/channel coordinates; no endpoint extrapolation.
- Original-channel consecutive-gap stopping, projected speed validation,
  substantial-overlap de-duplication, and polyline simplification for editing.
- 0 m/s lower speed bound means disabled lower-speed filtering; no division by
  zero. Existing annotations are not an input and never constrain detection.
- Peak arrays are cached; seeds are budgeted across time/space/direction/polarity.

The original spatial resampling, spatial bandpass, absolute amplitude/noise
thresholds, surface-wave window extraction, and dispersion imaging workflow
are not imported into the viewer. Their site assumptions do not describe this
BIN geometry. The separate existing beam backend retains its original behavior.

## Validation

Run `test/das_veh_tracking_check.py` for full-rate, polarity/direction, empty
results, missing channels, measured endpoints, static/noise rejection, projected
speed, likelihood equivalence, cross-file coordinates, cancellation and review.
`test/das_veh_real_check.py` reads only `das_context` from a local source project;
it does not use its annotation geometries or labels.

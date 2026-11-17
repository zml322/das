/** Preserve extrema in each bucket instead of periodically sampling zero crossings. */
export function waveformWindow(values: number[], samplingRate: number, seconds = 1.2, pointBudget = 320) {
  const rate = Number.isFinite(samplingRate) && samplingRate > 0 ? samplingRate : 1000;
  const count = Math.min(values.length, Math.max(1, Math.round(rate * seconds)));
  const window = values.slice(-count);
  const buckets = Math.max(1, Math.floor(pointBudget / 2));
  const points: { index: number; value: number }[] = [];
  if (window.length <= pointBudget) {
    window.forEach((value, index) => points.push({ index, value }));
  } else {
    for (let bucket = 0; bucket < buckets; bucket++) {
      const start = Math.floor(bucket * window.length / buckets);
      const end = Math.floor((bucket + 1) * window.length / buckets);
      let min = start, max = start;
      for (let i = start + 1; i < end; i++) {
        if (window[i] < window[min]) min = i;
        if (window[i] > window[max]) max = i;
      }
      for (const index of min === max ? [min] : [min, max].sort((a, b) => a - b)) {
        points.push({ index, value: window[index] });
      }
    }
  }
  return { points, count: window.length, duration: Math.max(0, window.length - 1) / rate };
}

export function chartMaximum(values: number[]) {
  const peak = values.reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  if (!peak) return 1;
  const step = Math.pow(10, Math.floor(Math.log10(peak))) / 2;
  return Math.ceil(peak * 1.05 / step) * step;
}

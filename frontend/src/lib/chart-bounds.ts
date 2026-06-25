/** Compute a stable Y-axis range from series data with light padding. */
export function computeYAxisBounds(
  y: number[],
  options?: { paddingRatio?: number; minSpan?: number }
): [number, number] | undefined {
  if (y.length === 0) return undefined;

  const paddingRatio = options?.paddingRatio ?? 0.08;
  const minSpan = options?.minSpan ?? 1e-6;

  let min = Infinity;
  let max = -Infinity;
  for (const value of y) {
    if (!Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }

  if (!Number.isFinite(min) || !Number.isFinite(max)) return undefined;

  if (min === max) {
    const half = Math.max(Math.abs(min) * 0.1, minSpan);
    return [min - half, max + half];
  }

  const span = max - min;
  const pad = Math.max(span * paddingRatio, minSpan);
  return [min - pad, max + pad];
}

/** Expand bounds so threshold lines remain visible inside the axis range. */
export function expandBoundsForThresholds(
  bounds: [number, number] | undefined,
  thresholds: number[]
): [number, number] | undefined {
  if (!bounds) return undefined;

  let [min, max] = bounds;
  for (const value of thresholds) {
    if (!Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }

  if (min === bounds[0] && max === bounds[1]) return bounds;

  const span = Math.max(max - min, 1e-6);
  const pad = span * 0.04;
  return [min - pad, max + pad];
}

/** Symmetric orbit bounds from X and Y orbit coordinates. */
export function computeOrbitAxisBounds(x: number[], y: number[]): [number, number] | undefined {
  const xBounds = computeYAxisBounds(x);
  const yBounds = computeYAxisBounds(y);
  if (!xBounds || !yBounds) return undefined;

  const limit = Math.max(
    Math.abs(xBounds[0]),
    Math.abs(xBounds[1]),
    Math.abs(yBounds[0]),
    Math.abs(yBounds[1])
  );
  const pad = limit * 0.08;
  return [-(limit + pad), limit + pad];
}

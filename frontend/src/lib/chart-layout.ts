/** Fraction of viewport height allocated to chart area in fullscreen mode. */
export const FULLSCREEN_CHART_HEIGHT_RATIO = 0.92;

/** Estimated header + hint + padding consumed by chart chrome in fullscreen. */
export const FULLSCREEN_CHROME_PX = 132;

export function computeFullscreenChartHeight(
  chromePx = FULLSCREEN_CHROME_PX,
  ratio = FULLSCREEN_CHART_HEIGHT_RATIO,
  viewportHeight?: number
): number {
  const vh =
    viewportHeight ?? (typeof window !== "undefined" ? window.innerHeight : 800);
  return Math.max(Math.round(vh * ratio) - chromePx, 360);
}

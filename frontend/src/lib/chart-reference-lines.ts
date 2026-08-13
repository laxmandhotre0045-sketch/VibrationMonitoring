import {
  INDUSTRIAL_REFERENCE_LINE,
  nyquistFrequencyHz,
  rpmToHz,
} from "./industrial-viz-standards";
import { ECHARTS_BRAND } from "./echarts-theme";
import { formatFrequencyHz } from "./echarts-theme";

type MarkLineDatum = Record<string, unknown>;

function verticalReferenceLine(
  frequencyHz: number,
  label: string,
  style: { color: string; type: "solid" | "dashed" | "dotted"; width: number; opacity: number }
): MarkLineDatum {
  return {
    xAxis: frequencyHz,
    name: label,
    lineStyle: {
      color: style.color,
      type: style.type,
      width: style.width,
      opacity: style.opacity,
    },
    label: {
      show: true,
      formatter: label,
      color: ECHARTS_BRAND.blue,
      fontFamily: ECHARTS_BRAND.font,
      fontSize: 10,
      position: "insideEndTop",
    },
  };
}

/**
 * Nyquist frequency marker at fs/2.
 * Reference: Smith, Scientist and Engineer's Guide to DSP — sampling theorem / FFT display.
 */
export function buildNyquistReferenceLine(sampleRateHz: number): MarkLineDatum | null {
  if (!Number.isFinite(sampleRateHz) || sampleRateHz <= 0) return null;
  const nyquist = nyquistFrequencyHz(sampleRateHz);
  return verticalReferenceLine(
    nyquist,
    `Nyquist ${formatFrequencyHz(nyquist)}`,
    INDUSTRIAL_REFERENCE_LINE.nyquist
  );
}

/**
 * Running-speed harmonic markers (1×, 2×, 3×).
 * Reference: Condition Monitoring with Vibration Signals — order/harmonic analysis.
 */
export function buildHarmonicReferenceLines(
  rpm: number,
  orders: number[] = [1, 2, 3]
): MarkLineDatum[] {
  if (!Number.isFinite(rpm) || rpm <= 0) return [];
  const fundamentalHz = rpmToHz(rpm);
  return orders.map((order) =>
    verticalReferenceLine(
      fundamentalHz * order,
      `${order}× (${formatFrequencyHz(fundamentalHz * order)})`,
      INDUSTRIAL_REFERENCE_LINE.harmonic
    )
  );
}

export function mergeSpectrumReferenceLines(
  ...groups: Array<MarkLineDatum | MarkLineDatum[] | null | undefined>
): MarkLineDatum[] {
  const merged: MarkLineDatum[] = [];
  for (const group of groups) {
    if (!group) continue;
    if (Array.isArray(group)) merged.push(...group);
    else merged.push(group);
  }
  return merged;
}

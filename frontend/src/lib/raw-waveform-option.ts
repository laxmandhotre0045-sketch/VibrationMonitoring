/**
 * ECharts option for the raw 25 kSPS waveform.
 *
 * X = timestamp_ (seconds, exactly as stored), Y = raw sample value. Nothing is
 * filtered, smoothed, averaged or resampled here — this draws the samples the device
 * measured. Windowing happens server-side; whatever arrives is plotted as-is.
 */
import type { EChartsOption } from "echarts";
import {
  baseAxisStyle,
  baseTooltip,
  CHART_GRID,
  CHART_TOOLBOX_OFF,
  CHART_X_AXIS_DATA_ZOOM,
  ECHARTS_BRAND,
  industrialAxisConfig,
} from "./echarts-theme";
import { INDUSTRIAL_AXIS_GRID } from "./industrial-viz-standards";
import type { RawSamplesResponse } from "@/types/raw-vibration";

const TRACE_COLOR = ECHARTS_BRAND.blue;

/** Seconds axis: 25 kSPS steps are 40 microseconds, so ms/us resolution is needed. */
export function formatSeconds(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1) return `${value.toFixed(4)} s`;
  if (abs >= 0.001) return `${(value * 1000).toFixed(2)} ms`;
  return `${(value * 1e6).toFixed(1)} µs`;
}

export function formatRawValue(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs >= 0.001 && abs < 10000) return value.toPrecision(6);
  return value.toExponential(4);
}

export interface BuildRawWaveformArgs {
  data: RawSamplesResponse;
  channel: number;
}

export function buildRawWaveformOption({ data, channel }: BuildRawWaveformArgs): EChartsOption {
  const key = `ch${channel}`;
  const points: [number, number][] = [];
  for (const sample of data.samples) {
    const v = sample[key];
    if (typeof v === "number" && Number.isFinite(v)) {
      points.push([sample.timestamp_, v]);
    }
  }

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    grid: CHART_GRID,
    tooltip: {
      ...baseTooltip,
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        const p = items[0];
        if (!p || !Array.isArray(p.value)) return "";
        const [t, v] = p.value as [number, number];
        const index = data.offset + Math.round(t * data.sampleRate) - data.offset;
        return [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">RAW · CH${channel}</span>`,
          `Time: <b>${formatSeconds(t)}</b>`,
          `Value: <b>${formatRawValue(v)}</b>`,
          `<span style="color:${ECHARTS_BRAND.muted};font-size:11px">sample ${
            Number.isFinite(index) ? index : "—"
          } · ${data.sampleRate.toLocaleString()} SPS</span>`,
        ].join("<br/>");
      },
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: "timestamp_ (s)",
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
      axisLabel: {
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
        formatter: (v: number) => formatSeconds(v),
      },
    },
    yAxis: {
      type: "value",
      name: `CH${channel} raw value`,
      nameLocation: "middle",
      nameGap: 52,
      scale: true,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
      axisLabel: {
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
        formatter: (v: number) => formatRawValue(v),
      },
    },
    series: [
      {
        type: "line",
        name: `CH${channel}`,
        data: points,
        showSymbol: false,
        smooth: false,
        // No `sampling` — decimating here would stop this being the raw signal.
        lineStyle: { color: TRACE_COLOR, width: 1.1 },
      },
    ],
  };
}

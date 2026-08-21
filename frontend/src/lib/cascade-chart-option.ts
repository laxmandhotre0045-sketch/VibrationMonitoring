/**
 * ECharts option for the 2D FFT cascade (stacked spectrum) plot.
 *
 * Built on the project's existing 2D chart theme and X-axis zoom config, so zoom, pan,
 * reset, crosshair, fullscreen and PNG export all behave exactly like the other charts.
 * Amplitude and frequency formatters are shared with the 3D waterfall so the same point
 * reads identically in both views.
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
import { formatAmplitude, formatFrequency } from "./waterfall-3d-option";
import type { CascadeModel, CascadeTrace } from "./cascade-transform";
import type { WaterfallResponse } from "@/types/waterfall";

/** Restrained ramp: older captures recede, newer ones step forward. */
const TRACE_COLOR_OLD = { r: 0x9d, g: 0xac, b: 0xbb };
const TRACE_COLOR_NEW = { r: 0x4a, g: 0x6b, b: 0x94 };

const SELECTED_COLOR = ECHARTS_BRAND.blue;
const PEAK_COLOR = ECHARTS_BRAND.orange;

const TRACE_WIDTH = 1;
const SELECTED_WIDTH = 2.1;

export function traceRampColor(index: number, total: number): string {
  const t = total > 1 ? index / (total - 1) : 1;
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  const r = mix(TRACE_COLOR_OLD.r, TRACE_COLOR_NEW.r);
  const g = mix(TRACE_COLOR_OLD.g, TRACE_COLOR_NEW.g);
  const b = mix(TRACE_COLOR_OLD.b, TRACE_COLOR_NEW.b);
  return `rgb(${r}, ${g}, ${b})`;
}

function row(label: string, value: string, strong = true): string {
  const rendered = strong ? `<b>${value}</b>` : value;
  return `<div style="display:flex;gap:14px;justify-content:space-between"><span style="color:${ECHARTS_BRAND.muted}">${label}</span>${rendered}</div>`;
}

export interface CascadeTooltipContext {
  model: CascadeModel;
  meta: WaterfallResponse;
  /** Capture the tooltip should describe — hovered trace, else the selected one. */
  getFocusCaptureNumber: () => number | null;
  /** Estimated shaft speed for the selected capture, in Hz. Null when unavailable. */
  getEstimatedShaftHz: () => number | null;
  getSelectedCaptureNumber: () => number | null;
}

interface AxisTooltipParam {
  seriesIndex?: number;
  seriesName?: string;
  dataIndex?: number;
  value?: unknown;
}

function traceByCaptureNumber(
  model: CascadeModel,
  captureNumber: number | null
): CascadeTrace | undefined {
  if (captureNumber == null) return undefined;
  return model.traces.find((t) => t.captureNumber === captureNumber);
}

function formatTimestamp(iso: string): string | null {
  const stamp = new Date(iso);
  return Number.isNaN(stamp.getTime()) ? null : stamp.toLocaleString();
}

export function buildCascadeTooltipFormatter(ctx: CascadeTooltipContext) {
  const { model, meta } = ctx;

  return (raw: AxisTooltipParam | AxisTooltipParam[]): string => {
    const params = Array.isArray(raw) ? raw : [raw];
    if (params.length === 0) return "";

    const focusNumber = ctx.getFocusCaptureNumber();
    const trace = traceByCaptureNumber(model, focusNumber) ?? model.traces[model.traces.length - 1];
    if (!trace) return "";

    const param =
      params.find((p) => p.seriesIndex === trace.captureIndex) ?? params[0];
    const value = param?.value;
    const frequency = Array.isArray(value) ? (value[0] as number) : undefined;
    if (frequency === undefined || !Number.isFinite(frequency)) return "";

    const dataIndex = param?.dataIndex ?? -1;
    const amplitude =
      dataIndex >= 0 && dataIndex < trace.amplitudes.length
        ? trace.amplitudes[dataIndex]
        : undefined;

    const lines = [
      `<div style="font-weight:600;color:${ECHARTS_BRAND.blue};margin-bottom:5px">${
        meta.plot_type === "envelope_spectrum" ? "Envelope spectrum" : "FFT spectrum"
      }</div>`,
      row("Capture", `#${trace.captureNumber}`),
    ];

    const timestamp = formatTimestamp(trace.capturedAt);
    if (timestamp) lines.push(row("Timestamp", timestamp));

    lines.push(row("Frequency", `${formatFrequency(frequency)} Hz`));

    if (amplitude !== undefined && Number.isFinite(amplitude)) {
      const unit = meta.z_label.match(/\(([^)]+)\)/)?.[1] ?? "";
      lines.push(row("Amplitude", `${formatAmplitude(amplitude)}${unit ? ` ${unit}` : ""}`));
    }

    if (trace.peakFrequencies.has(Math.round(frequency * 1000) / 1000)) {
      lines.push(row("Peak", "Yes"));
    }

    lines.push(row("Channel", `CH ${meta.channel + 1}`));
    if (meta.orientation) lines.push(row("Direction", meta.orientation));
    if (meta.sensor_label) lines.push(row("Sensor", meta.sensor_label));

    // Derived from the stored FFT, never measured — only offered for the selected capture.
    const shaftHz = ctx.getEstimatedShaftHz();
    if (
      shaftHz != null &&
      Number.isFinite(shaftHz) &&
      shaftHz > 0 &&
      trace.captureNumber === ctx.getSelectedCaptureNumber()
    ) {
      lines.push(
        row("Est. shaft speed", `${Math.round(shaftHz * 60).toLocaleString()} RPM`)
      );
    }

    return `<div style="min-width:220px;font-size:12px;line-height:1.6">${lines.join("")}</div>`;
  };
}

export interface BuildCascadeOptionArgs {
  model: CascadeModel;
  meta: WaterfallResponse;
  selectedCaptureNumber: number | null;
  showPeaks: boolean;
  tooltipFormatter: ReturnType<typeof buildCascadeTooltipFormatter>;
}

export function buildCascadeChartOption({
  model,
  meta,
  selectedCaptureNumber,
  showPeaks,
  tooltipFormatter,
}: BuildCascadeOptionArgs): EChartsOption {
  const total = model.traces.length;

  // Roughly eight readable capture labels regardless of N.
  const labelStep = Math.max(1, Math.ceil(total / 8));

  const traceSeries = model.traces.map((trace) => {
    const isSelected = trace.captureNumber === selectedCaptureNumber;
    return {
      type: "line" as const,
      name: `Capture #${trace.captureNumber}`,
      data: trace.points,
      showSymbol: false,
      smooth: false,
      // Never let ECharts thin the data: dropped bins would hide real spectral peaks.
      sampling: undefined,
      lineStyle: {
        color: isSelected ? SELECTED_COLOR : traceRampColor(trace.captureIndex, total),
        width: isSelected ? SELECTED_WIDTH : TRACE_WIDTH,
        opacity: isSelected ? 1 : 0.75,
      },
      z: isSelected ? 12 : 2,
      emphasis: {
        focus: "series" as const,
        lineStyle: { width: SELECTED_WIDTH, color: ECHARTS_BRAND.amber, opacity: 1 },
      },
      blur: { lineStyle: { opacity: 0.28 } },
    };
  });

  const peakSeries =
    showPeaks && model.peaks.length > 0
      ? [
          {
            type: "scatter" as const,
            name: "Peaks",
            symbol: "circle",
            symbolSize: 5,
            z: 20,
            data: model.peaks.map((peak) => [peak.frequency, peak.displayY]),
            itemStyle: {
              color: PEAK_COLOR,
              opacity: 0.85,
              borderColor: "#FFFFFF",
              borderWidth: 0.6,
            },
            emphasis: { itemStyle: { color: SELECTED_COLOR, opacity: 1 } },
          },
        ]
      : [];

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    grid: { ...CHART_GRID, left: 74 },
    tooltip: {
      ...baseTooltip,
      trigger: "axis",
      axisPointer: {
        ...(baseTooltip.axisPointer ?? {}),
        type: "cross",
        snap: true,
      },
      formatter: tooltipFormatter,
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: meta.x_label,
      nameLocation: "middle",
      nameGap: 30,
      min: model.frequencyRange[0],
      max: model.frequencyRange[1],
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
        fontSize: 12,
        formatter: (value: number) => formatFrequency(value),
      },
    },
    yAxis: {
      type: "value",
      // Ticks are capture numbers, not amplitudes — the axis is a stacking device.
      name: "Capture # (stacked)",
      nameLocation: "middle",
      nameGap: 56,
      min: model.displayRange[0],
      max: model.displayRange[1],
      scale: false,
      interval: model.laneSpacing * labelStep,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      axisLabel: {
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
        formatter: (value: number) => {
          const captureNumber = Math.round(value / model.laneSpacing) + 1;
          if (captureNumber < 1 || captureNumber > total) return "";
          return `#${captureNumber}`;
        },
      },
    },
    series: [...traceSeries, ...peakSeries],
  };
}

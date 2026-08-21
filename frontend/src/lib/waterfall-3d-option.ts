/**
 * ECharts GL option for the 3D FFT waterfall.
 *
 * One line3D per capture plus a single scatter3D carrying every detected peak.
 * Axis roles (see waterfall-adapter for the coordinate contract):
 *   xAxis3D -> Frequency (Hz)
 *   yAxis3D -> Capture # (depth)
 *   zAxis3D -> |A| peak (vertical)
 */
import { ECHARTS_BRAND } from "./echarts-theme";
import type { WaterfallModel } from "./waterfall-adapter";
import type { WaterfallResponse } from "@/types/waterfall";

/** echarts-gl adds option keys the bundled EChartsOption type does not know about. */
export type Echarts3DOption = Record<string, unknown>;

export interface WaterfallCamera {
  alpha: number;
  beta: number;
  distance: number;
}

/** Looking slightly down and from the right — the classic waterfall reading angle. */
export const DEFAULT_WATERFALL_CAMERA: WaterfallCamera = {
  alpha: 22,
  beta: 38,
  distance: 205,
};

export const CAMERA_MIN_DISTANCE = 60;
export const CAMERA_MAX_DISTANCE = 480;

const AXIS_TEXT = "#2B3A47";
const AXIS_LINE = "#C9D2DB";
const SPLIT_LINE = "#E6EBF0";

/** 5.00e-5 style labels — amplitudes here are routinely below 1e-3. */
export function formatAmplitude(value: number): string {
  if (!Number.isFinite(value)) return "";
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 0.01 && magnitude < 10000) return value.toPrecision(3);
  return value.toExponential(2);
}

export function formatFrequency(value: number): string {
  if (!Number.isFinite(value)) return "";
  return Math.abs(value) >= 1000
    ? Math.round(value).toLocaleString()
    : value.toFixed(Math.abs(value) >= 10 ? 0 : 1);
}

function axisCommon(name: string) {
  return {
    name,
    type: "value" as const,
    nameTextStyle: {
      color: ECHARTS_BRAND.blue,
      fontSize: 13,
      fontWeight: 600,
      fontFamily: ECHARTS_BRAND.font,
    },
    axisLine: { lineStyle: { color: AXIS_LINE, width: 1 } },
    axisTick: { lineStyle: { color: AXIS_LINE } },
    axisLabel: {
      color: AXIS_TEXT,
      fontSize: 11,
      fontFamily: ECHARTS_BRAND.font,
      margin: 10,
    },
    splitLine: { lineStyle: { color: SPLIT_LINE, width: 1 } },
    axisPointer: { lineStyle: { color: ECHARTS_BRAND.amber } },
  };
}

/** Roughly five labelled captures on the depth axis, whatever N is. */
function captureAxisInterval(min: number, max: number): number {
  const span = Math.max(1, max - min);
  return Math.max(1, Math.round(span / 4));
}

export interface WaterfallTooltipContext {
  model: WaterfallModel;
  meta: WaterfallResponse;
}

interface TooltipParams {
  seriesName?: string;
  value?: unknown;
  data?: unknown;
}

function row(label: string, value: string): string {
  return `<div style="display:flex;gap:10px;justify-content:space-between"><span style="color:${ECHARTS_BRAND.muted}">${label}</span><b>${value}</b></div>`;
}

export function buildWaterfallTooltip(ctx: WaterfallTooltipContext) {
  const { model, meta } = ctx;
  return (raw: TooltipParams | TooltipParams[]): string => {
    const params = Array.isArray(raw) ? raw[0] : raw;
    const value = params?.value;
    if (!Array.isArray(value) || value.length < 3) return "";

    const [frequency, captureNumber, amplitude] = value as number[];
    const capture = model.captureByNumber.get(captureNumber);
    const isPeak = params?.seriesName === "Peaks";

    const lines = [
      `<div style="font-weight:600;color:${ECHARTS_BRAND.blue};margin-bottom:4px">${
        isPeak ? "Spectral peak" : meta.plot_type === "envelope_spectrum" ? "Envelope" : "FFT"
      }</div>`,
      row("Capture", `#${captureNumber}`),
    ];

    if (capture?.captured_at) {
      const stamp = new Date(capture.captured_at);
      if (!Number.isNaN(stamp.getTime())) {
        lines.push(row("Timestamp", stamp.toLocaleString()));
      }
    }

    lines.push(row("Frequency", `${formatFrequency(frequency)} Hz`));
    lines.push(row("Amplitude", formatAmplitude(amplitude)));
    if (isPeak) lines.push(row("Peak", "Yes"));

    const channel = capture?.channel ?? meta.channel;
    lines.push(row("Channel", `CH ${channel + 1}`));
    if (meta.orientation) lines.push(row("Direction", meta.orientation));
    if (meta.sensor_label) lines.push(row("Sensor", meta.sensor_label));
    if (meta.mounting_location) lines.push(row("Location", meta.mounting_location));
    if (capture?.original_filename) lines.push(row("File", capture.original_filename));

    return `<div style="min-width:200px;font-size:12px;line-height:1.55">${lines.join("")}</div>`;
  };
}

export interface BuildWaterfallOptionArgs {
  model: WaterfallModel;
  meta: WaterfallResponse;
  camera?: WaterfallCamera;
  showPeaks?: boolean;
}

export function buildWaterfall3DOption({
  model,
  meta,
  camera = DEFAULT_WATERFALL_CAMERA,
  showPeaks = true,
}: BuildWaterfallOptionArgs): Echarts3DOption {
  const { ranges, labels } = model;
  const [captureMin, captureMax] = ranges.capture;

  const spectrumSeries = model.lines.map((line) => ({
    type: "line3D",
    name: `Capture ${line.captureNumber}`,
    data: line.points,
    lineStyle: { color: line.color, width: 1.6, opacity: 0.95 },
    silent: false,
  }));

  const peakSeries =
    showPeaks && model.peaks.length > 0
      ? [
          {
            type: "scatter3D",
            name: "Peaks",
            symbol: "circle",
            symbolSize: 7,
            data: model.peaks.map((peak) => ({
              value: peak.point,
              itemStyle: {
                color: model.lines[peak.captureIndex]?.color ?? ECHARTS_BRAND.orange,
                opacity: 1,
                borderWidth: 1,
                borderColor: "#FFFFFF",
              },
            })),
            emphasis: {
              itemStyle: { color: ECHARTS_BRAND.orange, borderColor: ECHARTS_BRAND.blue, borderWidth: 2 },
            },
          },
        ]
      : [];

  return {
    backgroundColor: "#FFFFFF",
    animation: false,
    tooltip: {
      show: true,
      backgroundColor: "#FFFDF8",
      borderColor: ECHARTS_BRAND.amber,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: ECHARTS_BRAND.blue, fontFamily: ECHARTS_BRAND.font, fontSize: 12 },
      formatter: buildWaterfallTooltip({ model, meta }),
    },
    xAxis3D: {
      ...axisCommon(labels.x),
      min: ranges.frequency[0],
      max: ranges.frequency[1],
      axisLabel: { ...axisCommon(labels.x).axisLabel, formatter: formatFrequency },
    },
    yAxis3D: {
      ...axisCommon(labels.y),
      min: captureMin,
      max: captureMax,
      interval: captureAxisInterval(captureMin, captureMax),
      axisLabel: {
        ...axisCommon(labels.y).axisLabel,
        formatter: (value: number) => String(Math.round(value)),
      },
    },
    zAxis3D: {
      ...axisCommon(labels.z),
      min: ranges.amplitude[0],
      max: ranges.amplitude[1],
      axisLabel: { ...axisCommon(labels.z).axisLabel, formatter: formatAmplitude },
    },
    grid3D: {
      boxWidth: 200,
      boxDepth: 108,
      boxHeight: 78,
      environment: "#FFFFFF",
      axisPointer: {
        show: true,
        lineStyle: { color: ECHARTS_BRAND.amber, width: 1 },
        label: { color: ECHARTS_BRAND.blue, fontSize: 11, backgroundColor: "#FFFDF8" },
      },
      light: {
        main: { intensity: 1.05, shadow: false, alpha: 30, beta: 40 },
        ambient: { intensity: 0.45 },
      },
      viewControl: {
        projection: "perspective",
        autoRotate: false,
        damping: 0.86,
        rotateSensitivity: 1,
        zoomSensitivity: 1,
        panSensitivity: 1,
        rotateMouseButton: "left",
        panMouseButton: "middle",
        alpha: camera.alpha,
        beta: camera.beta,
        distance: camera.distance,
        minDistance: CAMERA_MIN_DISTANCE,
        maxDistance: CAMERA_MAX_DISTANCE,
      },
    },
    series: [...spectrumSeries, ...peakSeries],
  };
}

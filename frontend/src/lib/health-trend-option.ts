import type { EChartsOption } from "echarts";
import type { HealthMetricTrend } from "@/types/health-status";
import {
  baseAxisStyle,
  baseTooltip,
  CHART_X_AXIS_DATA_ZOOM,
  ECHARTS_BRAND,
  industrialAxisConfig,
} from "./echarts-theme";
import { INDUSTRIAL_AXIS_GRID } from "./industrial-viz-standards";

// containLabel lets the axis labels reserve their own room. A fixed left gutter
// is not enough for a small reading like 0.000653, so the labels used to run
// under the plot and collide with the axis-pointer flag.
//
// `top` clears the in-plot axis name; `bottom` clears the time-range slider
// (22px tall, 8px off the floor). Everything else is as thin as the labels
// allow — on a KPI card the trace is the content.
/**
 * Above this many points the per-sample dots stop reading as measurements and
 * start reading as a thick line, so the trace falls back to a plain stroke.
 */
const MAX_SYMBOL_POINTS = 240;

const HEALTH_CHART_GRID = {
  left: 6,
  right: 16,
  top: 34,
  bottom: 42,
  containLabel: true,
} as const;

/**
 * Time-range slider for a KPI card.
 *
 * Same interaction as every other analysis chart — the shared inside+slider
 * pair — restyled for a card: a shorter track close to the floor, in the trace's
 * own blue rather than the workspace amber, and no drag read-out, which on a
 * 300px card covered the trace it was describing.
 */
const HEALTH_TREND_DATA_ZOOM = CHART_X_AXIS_DATA_ZOOM.map((zoom) =>
  zoom.type === "slider"
    ? {
        ...zoom,
        height: 22,
        bottom: 8,
        showDetail: false,
        brushSelect: false,
        borderColor: "transparent",
        backgroundColor: "rgba(21, 54, 109, 0.04)",
        fillerColor: "rgba(21, 54, 109, 0.10)",
        handleStyle: { color: "#FFFFFF", borderColor: ECHARTS_BRAND.blue, borderWidth: 1.5 },
        moveHandleStyle: { color: ECHARTS_BRAND.blue, opacity: 0.35 },
        dataBackground: {
          lineStyle: { color: "rgba(21, 54, 109, 0.35)", width: 1 },
          areaStyle: { color: "rgba(21, 54, 109, 0.06)" },
        },
        selectedDataBackground: {
          lineStyle: { color: ECHARTS_BRAND.blue, width: 1 },
          areaStyle: { color: "rgba(21, 54, 109, 0.14)" },
        },
      }
    : zoom
);

/**
 * A single reading, formatted for a tooltip or a headline value.
 *
 * Precision follows the magnitude here because there is only one number on
 * screen. Axis ticks do NOT use this — see `axisTickFormatter`.
 */
function formatMetricValue(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  if (unit === "%" || unit === "°C") return `${value.toFixed(1)}${unit}`;

  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(3);

  // A fixed 4 dp collapses a small reading: an RMS trend around 6.5e-4
  // rendered as "0.0007". Keep three significant digits instead.
  if (abs >= 1e-4) {
    const decimals = Math.min(8, Math.ceil(-Math.log10(abs)) + 2);
    return value.toFixed(decimals);
  }
  return value.toExponential(2);
}

/**
 * One decimal precision for the whole y axis, chosen from the span the axis
 * covers rather than from each tick's own magnitude.
 *
 * Per-value precision is what produced the ragged column in the screenshots —
 * an axis reading 0.000800 / 0.000700 / … / 0.000141, where the last label
 * carried three more digits than the ones above it and sat hard against its
 * neighbour. Ticks on one axis are a series; they have to be written alike.
 */
function axisTickFormatter(values: number[]): (value: number) => string {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return (v) => String(v);

  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const span = max - min;
  // A flat trend still needs a scale: fall back to the value's own magnitude.
  const reference = span > 0 ? span : Math.abs(max) || 1;
  const step = reference / (INDUSTRIAL_AXIS_GRID.splitNumber || 5);

  // Below this, decimals stop being readable and every tick goes exponential.
  if (step < 1e-6) return (v) => v.toExponential(2);

  const decimals = Math.min(8, Math.max(0, Math.ceil(-Math.log10(step)) + 1));
  return (v) => (Number.isFinite(v) ? v.toFixed(decimals) : "");
}

/**
 * Elapsed time within the capture.
 *
 * `trend_x` is the midpoint of each of the 32 segments, in seconds from the
 * start of the capture (`mid / sampling_rate_hz` in the backend's
 * `extract_segment_trends`). A block at 25.6 kHz spans well under a second, so
 * seconds alone would label every tick "0" — hence the millisecond form.
 */
function formatElapsed(seconds: number, spanSeconds: number): string {
  if (!Number.isFinite(seconds)) return "";
  if (spanSeconds > 0 && spanSeconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  if (spanSeconds < 10) return `${seconds.toFixed(2)} s`;
  return `${seconds.toFixed(1)} s`;
}

export function buildHealthTrendOption(
  metric: HealthMetricTrend,
  channelLabel?: string
): EChartsOption {
  const seriesData = metric.trendX.map((x, i) => [x, metric.trendY[i]] as [number, number]);

  const xValues = metric.trendX.filter((v) => Number.isFinite(v));
  const xSpan = xValues.length > 1 ? Math.max(...xValues) - Math.min(...xValues) : 0;
  const formatYTick = axisTickFormatter(metric.trendY);

  const capturedAt = metric.capturedAt ? new Date(metric.capturedAt) : null;
  const captureValid = capturedAt !== null && !Number.isNaN(capturedAt.getTime());

  const axis = baseAxisStyle();
  const axisName = metric.unit
    ? `${metric.label.replace(/\s+Trend$/i, "")} (${metric.unit})`
    : metric.label.replace(/\s+Trend$/i, "");

  // The latest reading is the one the card's headline value quotes; marking it
  // on the trace is what ties the two together at a glance.
  const lastPoint = seriesData.length > 0 ? seriesData[seriesData.length - 1] : null;

  // A dot on every sample, so each vertex where the trend turns is visible as a
  // measured point rather than a corner the eye has to infer. A factor trend is
  // 32 segments, so they never crowd — but the guard keeps the trace clean if a
  // denser series is ever passed through here.
  const showSymbol = seriesData.length > 0 && seriesData.length <= MAX_SYMBOL_POINTS;

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    grid: HEALTH_CHART_GRID,
    dataZoom: HEALTH_TREND_DATA_ZOOM,
    tooltip: {
      ...baseTooltip,
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        const point = items[0];
        if (!point || !Array.isArray(point.value)) return "";
        const [x, y] = point.value as [number, number];
        const unitSuffix = metric.unit ? ` ${metric.unit}` : "";

        const lines = [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${metric.label}</span>`,
        ];

        // An absolute instant is more use than a bare offset when comparing a
        // reading against the capture timeline.
        if (captureValid) {
          const at = new Date(capturedAt!.getTime() + x * 1000);
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">${at.toLocaleString()}</span>`
          );
        } else {
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">+${formatElapsed(x, xSpan)}</span>`
          );
        }

        const prefix = channelLabel ? `${channelLabel}: ` : "";
        lines.push(`${prefix}<b>${formatMetricValue(y, metric.unit)}${unitSuffix}</b>`);
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      show: true,
      // No pinned min/max: ECharts picks round bounds, so the ticks land on
      // even intervals instead of hanging a ragged one off each end.
      scale: true,
      ...axis,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        ...axis.axisLabel,
        fontSize: 11,
        margin: 12,
        hideOverlap: true,
        formatter: (v: number) => formatElapsed(v, xSpan),
      },
      // A vertical rule under each time tick: it is what lets an eye carry a
      // spike down to the instant it happened without reaching for a crosshair.
      splitLine: {
        show: true,
        lineStyle: { color: ECHARTS_BRAND.grid, width: 1, type: "dashed" as const },
      },
    },
    yAxis: {
      type: "value",
      show: true,
      scale: true,
      // Sits inside the plot at the top-left, so the reader knows what the
      // column of numbers below it measures without leaving the chart.
      name: axisName,
      nameLocation: "end",
      nameGap: 14,
      nameTextStyle: {
        align: "left",
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
      },
      ...axis,
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        ...axis.axisLabel,
        fontSize: 11,
        margin: 10,
        formatter: formatYTick,
      },
      splitLine: {
        show: true,
        lineStyle: { color: ECHARTS_BRAND.grid, width: 1 },
      },
    },
    series: [
      {
        type: "line",
        data: seriesData,
        showSymbol,
        symbol: "circle",
        symbolSize: 5,
        itemStyle: {
          color: ECHARTS_BRAND.blue,
          borderColor: ECHARTS_BRAND.paper,
          borderWidth: 1,
        },
        emphasis: {
          scale: 1.6,
          itemStyle: { color: ECHARTS_BRAND.blue, borderColor: ECHARTS_BRAND.paper },
        },
        // Diagnostic data: a spline invents values between segments and can
        // round off the very spike an analyst is looking for.
        smooth: false,
        lineStyle: { color: ECHARTS_BRAND.blue, width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(21, 54, 109, 0.16)" },
              { offset: 1, color: "rgba(21, 54, 109, 0.01)" },
            ],
          },
        },
        ...(lastPoint
          ? {
              markPoint: {
                symbol: "circle",
                symbolSize: 8,
                silent: true,
                label: { show: false },
                itemStyle: {
                  color: ECHARTS_BRAND.blue,
                  borderColor: ECHARTS_BRAND.paper,
                  borderWidth: 1.5,
                },
                data: [{ name: "Latest reading", coord: lastPoint }],
              },
            }
          : {}),
      },
    ],
  };
}

export function formatHealthMetricDisplay(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const suffix = unit ? ` ${unit}` : "";
  return `${formatMetricValue(value, unit)}${suffix}`;
}

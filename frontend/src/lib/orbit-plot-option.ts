/**
 * ECharts option for the 2D casing orbit (Lissajous).
 *
 * This is a CARTESIAN parametric plot — X vibration against Y vibration, in time order.
 * It is deliberately not the polar coordinate system used by the vibration vector plot.
 *
 * 1:1 ASPECT RATIO
 * ----------------
 * Both axes are pinned to the same symmetric range [-R, +R] and the grid is given equal
 * pixel width and height, centred. A circular orbit therefore renders as a circle at any
 * container size, which is non-negotiable for orbit interpretation.
 */
import type { EChartsOption } from "echarts";
import { baseAxisStyle, ECHARTS_BRAND } from "./echarts-theme";
import type { CasingOrbitResponse } from "@/types/orbit";

const FILTERED_COLOR_EARLY = "#9DB6D4";
const FILTERED_COLOR_LATE = "#15366D";
const UNFILTERED_COLOR = "#C9D2DB";
const LATEST_COLOR = ECHARTS_BRAND.orange;

/** Headroom so the trace is not glued to the frame. */
const RANGE_HEADROOM = 1.12;

export function formatMicrons(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  if (magnitude === 0) return "0";
  if (magnitude >= 0.01 && magnitude < 10000) return value.toFixed(3);
  return value.toExponential(2);
}

/**
 * Symmetric range covering both axes equally.
 *
 * Using one shared range for X and Y is what makes equal *physical* scale possible —
 * per-axis autoscaling would stretch a circle into an ellipse.
 */
export function orbitRange(data: CasingOrbitResponse): number {
  let peak = 0;
  for (const v of data.x_data) peak = Math.max(peak, Math.abs(v));
  for (const v of data.y_data) peak = Math.max(peak, Math.abs(v));
  if (data.unfiltered_x) for (const v of data.unfiltered_x) peak = Math.max(peak, Math.abs(v));
  if (data.unfiltered_y) for (const v of data.unfiltered_y) peak = Math.max(peak, Math.abs(v));
  return peak > 0 ? peak * RANGE_HEADROOM : 1;
}

/**
 * Force equal physical scale by measuring the grid ECharts actually produced.
 *
 * Asking for a square grid is not enough: ECharts reserves space for axis names and
 * labels in ways that leave the plot box a few pixels off square, which visibly turns a
 * circular orbit into an ellipse. Instead of fighting the layout, the axis ranges are
 * widened on whichever axis got more pixels, so px-per-micrometre matches exactly.
 * Both ranges stay >= the data range, so nothing is ever clipped.
 *
 * Returns the applied ranges, or null when no correction was needed.
 */
export function enforceEqualScale(
  instance: {
    getModel?: () => unknown;
    setOption: (o: Record<string, unknown>, notMerge: boolean) => void;
    isDisposed: () => boolean;
  } | null | undefined,
  baseRange: number
): { rx: number; ry: number } | null {
  // Defensive throughout: this is display polish, and it runs from effects that can fire
  // before ECharts has applied an option (the viewport uses lazyUpdate, so getModel()
  // returns undefined for a tick). Throwing here would unmount the whole page.
  try {
    if (!instance || instance.isDisposed() || typeof instance.getModel !== "function") {
      return null;
    }
    const model = instance.getModel() as
      | {
          getComponent?: (t: string) => {
            coordinateSystem?: { getRect?: () => { width: number; height: number } };
          } | null;
        }
      | undefined;
    if (!model || typeof model.getComponent !== "function") return null;

    const rect = model.getComponent("grid")?.coordinateSystem?.getRect?.();
    if (!rect || !rect.width || !rect.height) return null;

    const pxPerUnit = Math.min(rect.width, rect.height) / (2 * baseRange);
    if (!Number.isFinite(pxPerUnit) || pxPerUnit <= 0) return null;

    const rx = rect.width / (2 * pxPerUnit);
    const ry = rect.height / (2 * pxPerUnit);

    instance.setOption({ xAxis: { min: -rx, max: rx }, yAxis: { min: -ry, max: ry } }, false);
    return { rx, ry };
  } catch {
    return null;
  }
}

interface TooltipParam {
  seriesName?: string;
  dataIndex?: number;
  value?: unknown;
}

function row(label: string, value: string): string {
  return `<div style="display:flex;gap:14px;justify-content:space-between"><span style="color:${ECHARTS_BRAND.muted}">${label}</span><b>${value}</b></div>`;
}

export function buildOrbitTooltip(data: CasingOrbitResponse) {
  const captured = new Date(data.captured_at);
  const stamp = Number.isNaN(captured.getTime()) ? null : captured.toLocaleString();
  const rpm = data.estimated_shaft_hz != null ? Math.round(data.estimated_shaft_hz * 60) : null;

  return (raw: TooltipParam | TooltipParam[]): string => {
    const params = Array.isArray(raw) ? raw[0] : raw;
    const i = params?.dataIndex;
    if (i === undefined || i < 0 || i >= data.x_data.length) return "";

    const unfiltered = params?.seriesName === "Unfiltered";
    const x = unfiltered && data.unfiltered_x ? data.unfiltered_x[i] : data.x_data[i];
    const y = unfiltered && data.unfiltered_y ? data.unfiltered_y[i] : data.y_data[i];

    const lines = [
      `<div style="font-weight:600;color:${ECHARTS_BRAND.blue};margin-bottom:5px">${
        unfiltered ? "Unfiltered casing motion" : `${data.harmonic}× filtered orbit`
      }</div>`,
    ];
    if (stamp) lines.push(row("Capture", stamp));
    lines.push(row("Elapsed", `${(data.elapsed_s[i] * 1000).toFixed(2)} ms`));
    lines.push(row("Revolution", data.revolution[i].toFixed(3)));
    lines.push(row(`X · ch${data.x_channel}`, `${formatMicrons(x)} ${data.amplitude_unit}`));
    lines.push(row(`Y · ch${data.y_channel}`, `${formatMicrons(y)} ${data.amplitude_unit}`));
    if (!unfiltered) {
      lines.push(row("Band", `${data.harmonic}× · ${data.centre_hz.toFixed(2)} Hz`));
      lines.push(
        row("Filter", `${data.lower_hz.toFixed(2)}–${data.upper_hz.toFixed(2)} Hz`)
      );
    }
    if (rpm != null) lines.push(row("Est. shaft speed", `${rpm.toLocaleString()} RPM`));
    return `<div style="min-width:240px;font-size:12px;line-height:1.6">${lines.join("")}</div>`;
  };
}

export interface BuildOrbitOptionArgs {
  data: CasingOrbitResponse;
  /** Square plot box side in pixels — drives the equal-scale grid. */
  boxSize: number;
  showUnfiltered: boolean;
  tooltipFormatter: ReturnType<typeof buildOrbitTooltip>;
}

export function buildOrbitChartOption({
  data,
  boxSize,
  showUnfiltered,
  tooltipFormatter,
}: BuildOrbitOptionArgs): EChartsOption {
  const range = orbitRange(data);
  const axis = baseAxisStyle();
  const unit = data.amplitude_unit;

  // Equal pixel extent for both axes; the component sizes the container square.
  const margin = 64;
  const plot = Math.max(80, boxSize - margin * 2);

  const filtered = data.x_data.map((x, i) => [x, data.y_data[i], data.elapsed_s[i]]);
  const last = filtered.length ? filtered[filtered.length - 1] : null;

  const axisCommon = (name: string) => ({
    type: "value" as const,
    name,
    nameLocation: "middle" as const,
    nameGap: 34,
    min: -range,
    max: range,
    scale: false as const,
    nameTextStyle: {
      color: ECHARTS_BRAND.blue,
      fontFamily: ECHARTS_BRAND.font,
      fontSize: 12,
      fontWeight: 500,
    },
    ...axis,
    axisLabel: {
      color: ECHARTS_BRAND.muted,
      fontFamily: ECHARTS_BRAND.font,
      fontSize: 10,
      formatter: (v: number) => formatMicrons(v),
    },
  });

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    // Square, centred plot box => 1 unit X occupies the same pixels as 1 unit Y.
    grid: { left: margin, top: margin, width: plot, height: plot, containLabel: false },
    tooltip: {
      trigger: "item",
      backgroundColor: ECHARTS_BRAND.plot,
      borderColor: ECHARTS_BRAND.amber,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: ECHARTS_BRAND.blue, fontFamily: ECHARTS_BRAND.font, fontSize: 12 },
      confine: true,
      formatter: tooltipFormatter,
    },
    // Colour encodes elapsed time only — never severity.
    //
    // It is applied to the scatter overlay, not the line: ECharts only supports
    // visualMap on the x or y dimension for line lineStyle, so colouring a line by a
    // third (time) dimension silently fails. Scatter accepts any dimension.
    visualMap: {
      type: "continuous",
      dimension: 2,
      min: data.elapsed_s.length ? data.elapsed_s[0] : 0,
      max: data.elapsed_s.length ? data.elapsed_s[data.elapsed_s.length - 1] : 1,
      // Index of the "Time" scatter, which shifts when the unfiltered overlay is on.
      seriesIndex: showUnfiltered ? 2 : 1,
      calculable: false,
      right: 4,
      bottom: 20,
      itemWidth: 10,
      itemHeight: 96,
      text: ["latest", "first"],
      textStyle: { color: ECHARTS_BRAND.muted, fontFamily: ECHARTS_BRAND.font, fontSize: 10 },
      inRange: { color: [FILTERED_COLOR_EARLY, FILTERED_COLOR_LATE] },
    },
    xAxis: axisCommon(`X · ch${data.x_channel} (${unit})`),
    yAxis: axisCommon(`Y · ch${data.y_channel} (${unit})`),
    series: [
      ...(showUnfiltered && data.unfiltered_x && data.unfiltered_y
        ? [
            {
              type: "line" as const,
              name: "Unfiltered",
              data: data.unfiltered_x.map((x, i) => [x, data.unfiltered_y![i]]),
              showSymbol: false,
              z: 2,
              lineStyle: { color: UNFILTERED_COLOR, width: 1, opacity: 0.9 },
            },
          ]
        : []),
      {
        type: "line",
        name: "Filtered",
        data: filtered.map((p) => [p[0], p[1]]),
        showSymbol: false,
        silent: true,
        z: 6,
        lineStyle: { color: FILTERED_COLOR_LATE, width: 1.4, opacity: 0.45 },
      },
      // Same points, carrying elapsed time so visualMap can grade them. This is the
      // hoverable layer and the one the colour bar describes.
      {
        type: "scatter",
        name: "Time",
        data: filtered,
        symbolSize: 3,
        z: 10,
        itemStyle: { opacity: 1 },
      },
      // Latest sample: shows which end of the trace is "now".
      ...(last
        ? [
            {
              type: "scatter" as const,
              name: "Latest",
              data: [[last[0], last[1]]],
              symbolSize: 11,
              z: 14,
              silent: true,
              itemStyle: { color: LATEST_COLOR, borderColor: "#FFFFFF", borderWidth: 1.5 },
            },
          ]
        : []),
    ],
  };
}

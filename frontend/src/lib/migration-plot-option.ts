/**
 * ECharts option for the 1x amplitude migration plot.
 *
 * X = vertical 1x amplitude, Y = horizontal 1x amplitude, one point per capture,
 * connected oldest -> newest. Both values are magnitudes, so the chart deliberately
 * occupies the positive quadrant only; no sign is ever manufactured to make it resemble
 * a centreline plot.
 *
 * Equal physical scale is enforced by sharing ONE rounded range across both axes, so a
 * given number of micrometres covers the same distance horizontally and vertically.
 */
import type { EChartsOption } from "echarts";
import { baseAxisStyle, ECHARTS_BRAND } from "./echarts-theme";
import type { MigrationPoint, OneXMigrationResponse } from "@/types/migration";

const TRAIL_COLOR = "#B9C6D6";
const EARLY_COLOR = "#9DB6D4";
const LATE_COLOR = "#15366D";
const START_COLOR = ECHARTS_BRAND.amber;
const LATEST_COLOR = ECHARTS_BRAND.orange;
const INVALID_COLOR = "#C4CBD3";

/** Engineering-friendly significant figures — never toFixed(1) on sub-micron values. */
export function formatAmplitude(value: number | null | undefined, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  let text: string;
  if (magnitude === 0) text = "0";
  else if (magnitude >= 1000) text = value.toExponential(3);
  else if (magnitude >= 0.001) text = value.toPrecision(3);
  else text = value.toExponential(3);
  return unit ? `${text} ${unit}` : text;
}

/**
 * Round an axis maximum up to a clean 1 / 2 / 2.5 / 5 x 10^n step.
 * Turns 0.19755196068429867 into 0.2 rather than printing the raw float.
 */
export function niceAxisMax(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const decade = Math.pow(10, exponent);
  const normalised = value / decade;
  const step = [1, 2, 2.5, 5, 10].find((s) => normalised <= s + 1e-12) ?? 10;
  return step * decade;
}

/** One shared bound for both axes keeps the geometry truthful. */
export function migrationAxisMax(data: OneXMigrationResponse): number {
  const peak = Math.max(data.summary.x_max, data.summary.y_max);
  return niceAxisMax(peak > 0 ? peak * 1.05 : 1);
}

function row(label: string, value: string): string {
  return `<div style="display:flex;gap:14px;justify-content:space-between"><span style="color:${ECHARTS_BRAND.muted}">${label}</span><b>${value}</b></div>`;
}

interface TooltipParam {
  seriesName?: string;
  dataIndex?: number;
}

export function buildMigrationTooltip(data: OneXMigrationResponse) {
  const unit = data.amplitude_unit;
  return (raw: TooltipParam | TooltipParam[]): string => {
    const params = Array.isArray(raw) ? raw[0] : raw;
    const i = params?.dataIndex;
    if (i === undefined || i < 0 || i >= data.points.length) return "";
    const p: MigrationPoint = data.points[i];

    const lines = [
      `<div style="font-weight:600;color:${ECHARTS_BRAND.blue};margin-bottom:5px">Capture #${p.sequence}</div>`,
    ];
    const stamp = new Date(p.captured_at);
    if (!Number.isNaN(stamp.getTime())) lines.push(row("Timestamp", stamp.toLocaleString()));

    lines.push(row(`Vertical 1× · ch${p.x_channel}`, formatAmplitude(p.x_amplitude, unit)));
    lines.push(row(`Horizontal 1× · ch${p.y_channel}`, formatAmplitude(p.y_amplitude, unit)));
    lines.push(row("Vector magnitude", formatAmplitude(p.vector_amplitude, unit)));
    if (p.vh_ratio != null) lines.push(row("V/H ratio", p.vh_ratio.toPrecision(3)));

    if (p.shaft_frequency_hz != null) {
      lines.push(row("Shaft frequency", `${p.shaft_frequency_hz.toPrecision(4)} Hz`));
    }
    if (p.shaft_rpm != null) {
      lines.push(row("Estimated shaft speed", `${Math.round(p.shaft_rpm).toLocaleString()} RPM`));
    }
    lines.push(
      row("Speed source", p.speed_source === "override" ? "Manual override" : "Estimated (FFT)")
    );
    if (p.relative_phase_deg != null) {
      const sign = p.relative_phase_deg > 0 ? "+" : "";
      lines.push(row("Relative V-H phase", `${sign}${p.relative_phase_deg.toFixed(1)}°`));
    }
    lines.push(row("Quality", p.quality));
    if (p.warnings.length) {
      lines.push(
        `<div style="margin-top:5px;max-width:280px;color:${ECHARTS_BRAND.muted};font-size:11px">${p.warnings[0]}</div>`
      );
    }
    return `<div style="min-width:250px;font-size:12px;line-height:1.6">${lines.join("")}</div>`;
  };
}

export interface BuildMigrationOptionArgs {
  data: OneXMigrationResponse;
  boxSize: number;
  tooltipFormatter: ReturnType<typeof buildMigrationTooltip>;
}

export function buildMigrationChartOption({
  data,
  boxSize,
  tooltipFormatter,
}: BuildMigrationOptionArgs): EChartsOption {
  const max = migrationAxisMax(data);
  const axis = baseAxisStyle();
  const unit = data.amplitude_unit;
  const margin = 70;
  const plot = Math.max(80, boxSize - margin * 2);

  const valid = data.points.filter((p) => p.quality !== "invalid");
  const trail = valid.map((p) => [p.x_amplitude, p.y_amplitude]);
  const timed = valid.map((p) => [
    p.x_amplitude,
    p.y_amplitude,
    new Date(p.captured_at).getTime(),
  ]);
  const invalid = data.points
    .filter((p) => p.quality === "invalid")
    .map((p) => [p.x_amplitude, p.y_amplitude]);

  const first = valid[0];
  const last = valid[valid.length - 1];
  const times = timed.map((t) => t[2]);

  const axisCommon = (name: string) => ({
    type: "value" as const,
    name,
    nameLocation: "middle" as const,
    nameGap: 40,
    min: 0,
    max,
    // 5 clean intervals across a rounded max gives readable engineering ticks.
    interval: max / 5,
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
      formatter: (v: number) => formatAmplitude(v),
    },
  });

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
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
    legend: {
      bottom: 4,
      left: "center",
      itemGap: 18,
      icon: "circle",
      textStyle: { color: ECHARTS_BRAND.muted, fontFamily: ECHARTS_BRAND.font, fontSize: 11 },
      data: ["Capture trajectory", "Start", "Latest"],
    },
    // Colour encodes capture time only — never severity.
    visualMap: {
      type: "continuous",
      dimension: 2,
      min: times.length ? Math.min(...times) : 0,
      max: times.length ? Math.max(...times) : 1,
      seriesIndex: 1,
      calculable: false,
      right: 4,
      top: "middle",
      itemWidth: 10,
      itemHeight: 90,
      text: ["newest", "oldest"],
      textStyle: { color: ECHARTS_BRAND.muted, fontFamily: ECHARTS_BRAND.font, fontSize: 10 },
      inRange: { color: [EARLY_COLOR, LATE_COLOR] },
    },
    xAxis: axisCommon(`Vertical 1× amplitude · ch${data.x_channel} (${unit})`),
    yAxis: axisCommon(`Horizontal 1× amplitude · ch${data.y_channel} (${unit})`),
    series: [
      {
        type: "line",
        name: "Capture trajectory",
        data: trail,
        showSymbol: false,
        silent: true,
        z: 3,
        lineStyle: { color: TRAIL_COLOR, width: 1.4 },
      },
      {
        // Hoverable layer; dataIndex maps 1:1 onto the valid points.
        type: "scatter",
        name: "Captures",
        data: timed,
        symbolSize: 9,
        z: 8,
        itemStyle: { borderColor: "#FFFFFF", borderWidth: 0.8 },
      },
      ...(invalid.length
        ? [
            {
              type: "scatter" as const,
              name: "Invalid",
              data: invalid,
              symbolSize: 7,
              symbol: "circle" as const,
              z: 5,
              itemStyle: { color: INVALID_COLOR, opacity: 0.7 },
            },
          ]
        : []),
      ...(first
        ? [
            {
              type: "scatter" as const,
              name: "Start",
              data: [[first.x_amplitude, first.y_amplitude]],
              symbol: "circle" as const,
              symbolSize: 15,
              z: 12,
              silent: true,
              itemStyle: {
                color: "transparent",
                borderColor: START_COLOR,
                borderWidth: 2.4,
              },
            },
          ]
        : []),
      ...(last
        ? [
            {
              type: "scatter" as const,
              name: "Latest",
              data: [[last.x_amplitude, last.y_amplitude]],
              symbol: "diamond" as const,
              symbolSize: 17,
              z: 14,
              silent: true,
              itemStyle: { color: LATEST_COLOR, borderColor: "#FFFFFF", borderWidth: 1.5 },
            },
          ]
        : []),
    ],
  };
}

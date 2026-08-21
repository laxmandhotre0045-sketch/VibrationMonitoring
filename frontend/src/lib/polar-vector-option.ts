/**
 * ECharts option for the polar / vibration vector plot.
 *
 * Angle convention (must match the backend's ANGLE_CONVENTION exactly):
 *   0 deg at 3 o'clock, positive counter-clockwise.
 *   -> startAngle: 0, clockwise: false
 *
 * Data format: every polar datum is [radius, angle]. Passing [x, y] here silently
 * produces a plausible-looking but wrong plot, so the transform builds the pairs once
 * and nothing else reorders them.
 */
import type { EChartsOption } from "echarts";
import {
  baseAxisStyle,
  ECHARTS_BRAND,
  formatAmplitudeWithUnit,
} from "./echarts-theme";
import type { PolarVectorModel, VectorPoint } from "./polar-vector-transform";
import type { VibrationVectorResponse } from "@/types/vector";

const REFERENCE_COLOR = ECHARTS_BRAND.amber;
const LATEST_COLOR = ECHARTS_BRAND.orange;
const PATH_COLOR = "#8FA0B3";

export function formatPhase(deg: number): string {
  if (!Number.isFinite(deg)) return "—";
  const sign = deg > 0 ? "+" : "";
  return `${sign}${deg.toFixed(1)}°`;
}

export function formatAmplitudeValue(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  const text =
    magnitude >= 0.01 && magnitude < 10000 ? value.toPrecision(4) : value.toExponential(3);
  return unit ? `${text} ${unit}` : text;
}

interface TooltipParam {
  seriesName?: string;
  dataIndex?: number;
  value?: unknown;
}

function row(label: string, value: string): string {
  return `<div style="display:flex;gap:14px;justify-content:space-between"><span style="color:${ECHARTS_BRAND.muted}">${label}</span><b>${value}</b></div>`;
}

export interface PolarTooltipContext {
  model: PolarVectorModel;
  meta: VibrationVectorResponse;
}

export function buildPolarVectorTooltip({ model, meta }: PolarTooltipContext) {
  const capturedAt = new Date(meta.captured_at);
  const stamp = Number.isNaN(capturedAt.getTime()) ? null : capturedAt.toLocaleString();

  return (raw: TooltipParam | TooltipParam[]): string => {
    const params = Array.isArray(raw) ? raw[0] : raw;
    const index = params?.dataIndex;
    if (index === undefined || index < 0 || index >= model.points.length) return "";
    const p: VectorPoint = model.points[index];

    const lines = [
      `<div style="font-weight:600;color:${ECHARTS_BRAND.blue};margin-bottom:5px">Vibration vector</div>`,
      row("Block", `#${p.blockIndex + 1} of ${model.points.length}`),
    ];
    if (stamp) lines.push(row("Capture time", stamp));
    lines.push(row("Block offset", `${p.timeS.toFixed(4)} s`));
    lines.push(row("Frequency", `${meta.bin_hz.toFixed(2)} Hz (bin ${meta.bin_index})`));
    lines.push(row("Amplitude", formatAmplitudeValue(p.amplitude, model.amplitudeUnit)));
    lines.push(row("Relative phase", formatPhase(p.relativePhaseDeg)));
    lines.push(row("Channel", `CH ${meta.channel + 1}`));
    if (meta.orientation) lines.push(row("Direction", meta.orientation));
    if (meta.sensor_label) lines.push(row("Sensor", meta.sensor_label));
    if (model.estimatedRpm != null) {
      lines.push(row("Est. shaft speed", `${Math.round(model.estimatedRpm).toLocaleString()} RPM`));
    }
    if (p.isReference) {
      lines.push(
        `<div style="margin-top:5px;color:${ECHARTS_BRAND.muted};font-size:11px">Phase reference block (0° by definition)</div>`
      );
    }
    return `<div style="min-width:230px;font-size:12px;line-height:1.6">${lines.join("")}</div>`;
  };
}

export interface BuildPolarOptionArgs {
  model: PolarVectorModel;
  meta: VibrationVectorResponse;
  showPath: boolean;
  tooltipFormatter: ReturnType<typeof buildPolarVectorTooltip>;
}

export function buildPolarVectorChartOption({
  model,
  meta,
  showPath,
  tooltipFormatter,
}: BuildPolarOptionArgs): EChartsOption {
  const axis = baseAxisStyle();

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
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
    polar: { center: ["50%", "52%"], radius: "72%" },
    angleAxis: {
      type: "value",
      min: -180,
      max: 180,
      // 0 deg at 3 o'clock, positive counter-clockwise — matches atan2 and the backend.
      //
      // startAngle positions the axis MINIMUM, not the value 0. With min = -180 and
      // counter-clockwise winding, the -180 end must start at 180 deg so that value 0
      // lands half a turn later, at 3 o'clock. Setting this to 0 silently rotates the
      // whole plot by 180 deg.
      startAngle: 180,
      clockwise: false,
      interval: 30,
      axisLine: { lineStyle: { color: ECHARTS_BRAND.axis } },
      axisTick: { lineStyle: { color: ECHARTS_BRAND.axis } },
      splitLine: { lineStyle: { color: ECHARTS_BRAND.grid } },
      axisLabel: {
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
        formatter: (value: number) => `${value}°`,
      },
    },
    radiusAxis: {
      type: "value",
      min: 0,
      max: model.radiusMax,
      name: model.amplitudeUnit ? `Amplitude (${model.amplitudeUnit})` : "Amplitude",
      nameLocation: "end",
      nameGap: 12,
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
        formatter: (value: number) =>
          value === 0 ? "0" : formatAmplitudeValue(value, ""),
      },
      splitLine: { lineStyle: { color: ECHARTS_BRAND.grid } },
    },
    series: [
      // Locus through the block tips, in block order.
      ...(showPath && model.path.length > 1
        ? [
            {
              type: "line" as const,
              name: "Vector path",
              coordinateSystem: "polar" as const,
              data: model.path,
              showSymbol: false,
              silent: true,
              z: 2,
              lineStyle: { color: PATH_COLOR, width: 1.2, opacity: 0.85 },
            },
          ]
        : []),
      // Origin -> latest tip: the current vector.
      ...(model.latestVector.length === 2
        ? [
            {
              type: "line" as const,
              name: "Current vector",
              coordinateSystem: "polar" as const,
              data: model.latestVector,
              showSymbol: false,
              silent: true,
              z: 8,
              lineStyle: { color: LATEST_COLOR, width: 2.4 },
            },
          ]
        : []),
      // One scatter carrying every block, coloured by order. This is the hoverable layer,
      // and dataIndex maps 1:1 onto model.points for the tooltip.
      {
        type: "scatter",
        name: "Blocks",
        coordinateSystem: "polar",
        data: model.points.map((p) => ({
          value: p.point,
          itemStyle: {
            color: p.isLatest ? LATEST_COLOR : p.isReference ? REFERENCE_COLOR : p.color,
            borderColor: "#FFFFFF",
            borderWidth: p.isLatest || p.isReference ? 1.5 : 0.6,
          },
          symbolSize: p.isLatest ? 15 : p.isReference ? 12 : 8,
        })),
        z: 12,
        emphasis: { itemStyle: { color: ECHARTS_BRAND.blue, borderWidth: 2 } },
      },
    ],
  };
}

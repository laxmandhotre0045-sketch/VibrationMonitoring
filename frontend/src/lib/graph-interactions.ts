import type { EChartsType } from "echarts";

export function adaptiveLineWidth(visibleFraction: number, baseWidth = 1.5): number {
  const fraction = Math.max(visibleFraction, 0.005);
  const zoomFactor = 1 / fraction;
  return Math.max(0.35, Math.min(baseWidth, baseWidth / Math.sqrt(zoomFactor)));
}

export function readDataZoomRange(instance: EChartsType): { start: number; end: number } {
  const option = instance.getOption() as {
    dataZoom?: Array<{ start?: number; end?: number }>;
  };
  const ranges = option.dataZoom ?? [];
  for (const dz of ranges) {
    if (dz.start !== undefined && dz.end !== undefined) {
      return { start: dz.start, end: dz.end };
    }
  }
  return { start: 0, end: 100 };
}

export function zoomChart(instance: EChartsType, direction: "in" | "out") {
  const { start, end } = readDataZoomRange(instance);
  const span = end - start;
  const center = (start + end) / 2;
  const factor = direction === "in" ? 0.65 : 1.45;
  const newSpan = Math.min(100, Math.max(2, span * factor));
  const newStart = Math.max(0, center - newSpan / 2);
  const newEnd = Math.min(100, center + newSpan / 2);
  instance.dispatchAction({
    type: "dataZoom",
    start: newStart,
    end: newEnd,
  });
}

export function resetChartZoom(instance: EChartsType) {
  instance.dispatchAction({ type: "restore" });
  instance.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
}

export function autoscaleChart(instance: EChartsType) {
  instance.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
}

export function applyAdaptiveLineWidth(instance: EChartsType, baseWidth = 1.5) {
  if (instance.isDisposed()) return;

  const option = instance.getOption() as {
    series?: Array<{ data?: unknown; type?: string }>;
  };
  const series = option.series ?? [];
  if (series.length === 0) return;

  const hasRenderableData = series.some((entry) => {
    if (!Array.isArray(entry.data)) return false;
    return entry.data.length > 0;
  });
  if (!hasRenderableData) return;

  const { start, end } = readDataZoomRange(instance);
  const span = Math.max(end - start, 0.01);
  const width = adaptiveLineWidth(span / 100, baseWidth);

  instance.setOption(
    {
      series: series.map(() => ({
        lineStyle: { width },
      })),
    },
    false,
    false
  );
}

export function setCrosshairEnabled(instance: EChartsType, enabled: boolean) {
  instance.setOption(
    {
      tooltip: {
        axisPointer: {
          type: enabled ? "cross" : "line",
          crossStyle: {
            color: "#D98C00",
            width: 1,
            type: "dashed",
          },
          lineStyle: {
            color: "#D98C00",
            width: 1,
            type: "dashed",
          },
        },
      },
    },
    false,
    false
  );
}

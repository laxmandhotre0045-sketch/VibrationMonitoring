import React, { memo, useCallback, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { autoscaleTitleFor, chartHintFor } from "@/lib/chart-hints";
import { GRAPH_PRIMARY_HEIGHT } from "@/lib/chart-constants";
import {
  computeChartStatistics,
  sliceValuesByZoomPercent,
  type ChartStatistics,
} from "@/lib/chart-statistics";
import { buildDiagnosticChartOption } from "@/lib/echarts-diagnostic-option";
import type { ThresholdOverlayOptions } from "@/lib/threshold-overlay";
import {
  autoscaleChart,
  resetChartZoom,
  setCrosshairEnabled,
  zoomChart,
} from "@/lib/graph-interactions";
import { resolveSampleRateHz } from "@/lib/waveform-time-axis";
import {
  EchartsGraphViewport,
  GraphStatisticsPanel,
  GraphWorkspace,
  ThresholdZoneLegend,
} from "@/components/charts";
import { parseUnitFromAxisLabel } from "@/lib/industrial-viz-standards";

interface EchartsDiagnosticChartProps {
  plot: PlotSeries;
  height?: number;
  samplingRateHz?: number;
}

function readMetadataNumber(
  metadata: Record<string, unknown> | undefined,
  keys: string[]
): number | null {
  if (!metadata) return null;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function EchartsDiagnosticChartInner({
  plot,
  height = GRAPH_PRIMARY_HEIGHT,
  samplingRateHz,
}: EchartsDiagnosticChartProps) {
  const chartRef = useRef<ReactECharts>(null);
  const instanceRef = useRef<EChartsType | null>(null);
  const [crosshairEnabled, setCrosshairEnabledState] = useState(true);
  const [showThresholds, setShowThresholds] = useState(true);
  const [zoomRange, setZoomRange] = useState({ start: 0, end: 100 });

  const overlayOptions = useMemo(
    (): ThresholdOverlayOptions => ({
      showThresholds,
      showShading: showThresholds,
      showCrossings: showThresholds,
    }),
    [showThresholds]
  );

  const option = useMemo(
    () => buildDiagnosticChartOption(plot, samplingRateHz, overlayOptions),
    [plot, samplingRateHz, overlayOptions]
  );

  const metadata = plot.metadata as Record<string, unknown> | undefined;
  const statsContext = useMemo(
    () => ({
      samplingRateHz: resolveSampleRateHz(plot, samplingRateHz),
      rpm: readMetadataNumber(metadata, ["rpm", "speed_rpm", "shaft_rpm"]),
      sensorStatus: String(metadata?.sensor_status ?? metadata?.status ?? "Online"),
    }),
    [metadata, plot, samplingRateHz]
  );

  const statistics = useMemo((): ChartStatistics => {
    const visible = sliceValuesByZoomPercent(plot.y, zoomRange.start, zoomRange.end);
    return computeChartStatistics(visible, statsContext);
  }, [plot.y, zoomRange, statsContext]);

  const getInstance = useCallback(() => {
    const instance = chartRef.current?.getEchartsInstance() as EChartsType | undefined;
    if (instance) instanceRef.current = instance;
    return instance;
  }, []);

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) instance.resize();
  }, [getInstance]);

  const handleZoomIn = useCallback(() => {
    const instance = getInstance();
    if (instance) zoomChart(instance, "in");
  }, [getInstance]);

  const handleZoomOut = useCallback(() => {
    const instance = getInstance();
    if (instance) zoomChart(instance, "out");
  }, [getInstance]);

  const handleReset = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    resetChartZoom(instance);
    setZoomRange({ start: 0, end: 100 });
  }, [getInstance]);

  const handleAutoscale = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    autoscaleChart(instance);
    setZoomRange({ start: 0, end: 100 });
  }, [getInstance]);

  const handleCrosshair = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    const next = !crosshairEnabled;
    setCrosshairEnabledState(next);
    setCrosshairEnabled(instance, next);
  }, [crosshairEnabled, getInstance]);

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    const dataUrl = instance.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#FFFDF8",
    });
    const link = document.createElement("a");
    link.download = `sensovibe-${plot.plot_type}-ch${plot.channel}.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, plot.plot_type, plot.channel]);

  const amplitudeUnit = useMemo(
    () => parseUnitFromAxisLabel(plot.y_label),
    [plot.y_label]
  );

  const statisticsPanel = useMemo(
    () => (
      <div className="space-y-g2">
        <GraphStatisticsPanel stats={statistics} amplitudeUnit={amplitudeUnit || undefined} />
        <ThresholdZoneLegend visible={showThresholds} />
      </div>
    ),
    [statistics, amplitudeUnit, showThresholds]
  );

  return (
    <GraphWorkspace
      title={plot.title}
      subtitle={
        <span>
          {plot.x_label} · {plot.y_label}
        </span>
      }
      height={height}
      variant="primary"
      hint={chartHintFor(plot.plot_type)}
      channelLabel={`CH-${plot.channel + 1}`}
      onZoomIn={handleZoomIn}
      onZoomOut={handleZoomOut}
      onPan={() => undefined}
      onReset={handleReset}
      onCrosshair={handleCrosshair}
      onToggleThresholds={() => setShowThresholds((value) => !value)}
      onAutoscale={handleAutoscale}
      onExport={handleExport}
      onChartResize={handleResize}
      isCrosshairActive={crosshairEnabled}
      thresholdsVisible={showThresholds}
      statistics={statisticsPanel}
      toolbarActions={[
        "zoomIn",
        "zoomOut",
        "pan",
        "reset",
        "crosshair",
        "thresholds",
        "autoscale",
        "export",
        "fullscreen",
      ]}
    >
      {({ height: chartHeight, isFullscreen }) => (
        <EchartsGraphViewport
          chartRef={chartRef}
          option={option}
          chartHeight={chartHeight}
          isFullscreen={isFullscreen}
          crosshairEnabled={crosshairEnabled}
          onDataZoom={setZoomRange}
          onChartReady={(instance) => {
            instanceRef.current = instance;
          }}
        />
      )}
    </GraphWorkspace>
  );
}

/** Unified Apache ECharts diagnostic chart for all plot types. */
export const EchartsDiagnosticChart = memo(EchartsDiagnosticChartInner);

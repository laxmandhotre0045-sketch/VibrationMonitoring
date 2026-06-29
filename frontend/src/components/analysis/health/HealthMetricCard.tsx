import React, { useCallback, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import type { HealthMetricTrend } from "@/types/health-status";
import { buildHealthTrendOption, formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { hasConfiguredThresholds, resolveGraphThresholdsFromHealth } from "@/lib/threshold-overlay";
import { GRAPH_COMPACT_HEIGHT } from "@/lib/chart-constants";
import {
  autoscaleChart,
  resetChartZoom,
  setCrosshairEnabled,
  zoomChart,
} from "@/lib/graph-interactions";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import { cn } from "@/lib/utils";

interface HealthMetricCardProps {
  metric: HealthMetricTrend;
  channelLabel: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  trendFooterLabel?: string;
  className?: string;
}

const STATUS_STYLES = {
  healthy: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/25",
  warning: "bg-signal-light/15 text-signal-dark border-signal-light/40",
  danger: "bg-destructive/10 text-destructive border-destructive/25",
  neutral: "bg-muted/40 text-muted-foreground border-border",
} as const;

const STATUS_LABELS = {
  healthy: "OK",
  warning: "Warning",
  danger: "Danger",
  neutral: "Trend",
} as const;

export function HealthMetricCard({
  metric,
  channelLabel,
  onRefresh,
  isRefreshing = false,
  trendFooterLabel = "Segment trend",
  className,
}: HealthMetricCardProps) {
  const chartRef = useRef<ReactECharts>(null);
  const [crosshairEnabled, setCrosshairEnabledState] = useState(true);
  const [showThresholds, setShowThresholds] = useState(true);

  const overlayOptions = useMemo(
    () => ({
      showThresholds,
      showShading: showThresholds,
      showCrossings: showThresholds,
    }),
    [showThresholds]
  );

  const hasThresholdOverlays = useMemo(
    () =>
      hasConfiguredThresholds(
        resolveGraphThresholdsFromHealth(
          metric.warningThreshold,
          metric.dangerThreshold,
          metric.normalThreshold
        )
      ),
    [metric.warningThreshold, metric.dangerThreshold, metric.normalThreshold]
  );

  const option = useMemo(
    () => buildHealthTrendOption(metric, overlayOptions),
    [metric, overlayOptions]
  );

  const showThresholdToggle = hasThresholdOverlays;

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

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
    if (instance) resetChartZoom(instance);
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
    link.download = `sensovibe-health-${metric.key}-${channelLabel.toLowerCase()}.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, metric.key, channelLabel]);

  const headerExtra = (
    <span
      className={cn(
        "inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold",
        STATUS_STYLES[metric.status]
      )}
    >
      {STATUS_LABELS[metric.status]}
    </span>
  );

  return (
    <GraphWorkspace
      className={cn("h-full", className)}
      variant="compact"
      height={GRAPH_COMPACT_HEIGHT}
      title={metric.label}
      subtitle={
        <span>
          {metric.unit && `(${metric.unit}) · `}
          <strong className="text-brand">
            {metric.available
              ? formatHealthMetricDisplay(metric.value, metric.unit)
              : "N/A"}
          </strong>
        </span>
      }
      headerExtra={headerExtra}
      channelLabel={channelLabel}
      hint={trendFooterLabel}
      onZoomIn={metric.available ? handleZoomIn : undefined}
      onZoomOut={metric.available ? handleZoomOut : undefined}
      onReset={metric.available ? handleReset : undefined}
      onCrosshair={metric.available ? handleCrosshair : undefined}
      onToggleThresholds={
        showThresholdToggle ? () => setShowThresholds((value) => !value) : undefined
      }
      onAutoscale={metric.available ? () => autoscaleChart(getInstance()!) : undefined}
      onExport={metric.available ? handleExport : undefined}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      isCrosshairActive={crosshairEnabled}
      thresholdsVisible={showThresholds}
      onChartResize={handleResize}
      toolbarActions={[
        "zoomIn",
        "zoomOut",
        "reset",
        "crosshair",
        ...(showThresholdToggle ? (["thresholds"] as const) : []),
        "refresh",
        "export",
        "fullscreen",
      ]}
    >
      {({ height: chartHeight, isFullscreen }) =>
        metric.available ? (
          <EchartsGraphViewport
            chartRef={chartRef}
            option={option}
            chartHeight={chartHeight}
            isFullscreen={isFullscreen}
            crosshairEnabled={crosshairEnabled}
            baseLineWidth={1.75}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-3">
            <p className="text-sm text-muted-foreground text-center">
              Not available for this capture
            </p>
          </div>
        )
      }
    </GraphWorkspace>
  );
}

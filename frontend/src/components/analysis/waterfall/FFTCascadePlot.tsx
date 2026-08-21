import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import {
  autoscaleChart,
  resetChartZoom,
  setCrosshairEnabled,
  zoomChart,
} from "@/lib/graph-interactions";
import { buildCascadeModel } from "@/lib/cascade-transform";
import {
  buildCascadeChartOption,
  buildCascadeTooltipFormatter,
} from "@/lib/cascade-chart-option";
import { formatFrequency } from "@/lib/waterfall-3d-option";
import type { WaterfallModel } from "@/lib/waterfall-adapter";
import { useEstimatedShaftSpeed } from "@/hooks/useEstimatedShaftSpeed";
import { WATERFALL_MODE_LABELS, type WaterfallResponse } from "@/types/waterfall";
import { cn } from "@/lib/utils";

interface FFTCascadePlotProps {
  model: WaterfallModel;
  meta: WaterfallResponse;
  height: number;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

interface SeriesEventParams {
  seriesIndex?: number;
  componentType?: string;
}

function formatHz(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${formatFrequency(value)} Hz`;
}

function headerFacts(meta: WaterfallResponse, traceCount: number): string[] {
  const facts: string[] = [`CH ${meta.channel + 1}`];
  if (meta.orientation) facts.push(meta.orientation.toUpperCase());
  if (meta.window) facts.push(meta.window);
  if (meta.fft_lines) facts.push(`${meta.fft_lines.toLocaleString()}-pt`);
  facts.push(`${traceCount} capture${traceCount === 1 ? "" : "s"}`);
  return facts;
}

function FFTCascadePlotInner({
  model,
  meta,
  height,
  onRefresh,
  isRefreshing = false,
}: FFTCascadePlotProps) {
  const chartRef = useRef<ReactECharts>(null);
  const [crosshairEnabled, setCrosshairEnabledState] = useState(true);
  const [showPeaks, setShowPeaks] = useState(true);

  // Newest capture is highlighted by default — the top trace in the reference layout.
  const newestCaptureNumber =
    model.lines.length > 0 ? model.lines[model.lines.length - 1].captureNumber : null;
  const [selectedCaptureNumber, setSelectedCaptureNumber] = useState<number | null>(
    newestCaptureNumber
  );

  useEffect(() => {
    setSelectedCaptureNumber(newestCaptureNumber);
  }, [newestCaptureNumber]);

  // Hover lives in a ref: the tooltip formatter reads it, so tracking it must not re-render.
  const hoveredCaptureRef = useRef<number | null>(null);
  const selectedRef = useRef<number | null>(selectedCaptureNumber);
  selectedRef.current = selectedCaptureNumber;

  const cascade = useMemo(
    () => buildCascadeModel(model, { heightPx: height }),
    [model, height]
  );

  const selectedTrace = useMemo(
    () => cascade.traces.find((t) => t.captureNumber === selectedCaptureNumber) ?? null,
    [cascade.traces, selectedCaptureNumber]
  );

  const shaftSpeed = useEstimatedShaftSpeed({
    uploadId: selectedTrace?.uploadId ?? null,
    channel: meta.channel,
  });
  const shaftHzRef = useRef<number | null>(null);
  shaftHzRef.current = shaftSpeed.hz;

  const tooltipFormatter = useMemo(
    () =>
      buildCascadeTooltipFormatter({
        model: cascade,
        meta,
        getFocusCaptureNumber: () => hoveredCaptureRef.current ?? selectedRef.current,
        getEstimatedShaftHz: () => shaftHzRef.current,
        getSelectedCaptureNumber: () => selectedRef.current,
      }),
    [cascade, meta]
  );

  const option = useMemo(
    () =>
      buildCascadeChartOption({
        model: cascade,
        meta,
        selectedCaptureNumber,
        showPeaks,
        tooltipFormatter,
      }),
    [cascade, meta, selectedCaptureNumber, showPeaks, tooltipFormatter]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  const handleChartReady = useCallback(
    (instance: EChartsType) => {
      const captureOf = (params: SeriesEventParams): number | null => {
        const index = params.seriesIndex;
        if (index === undefined || index < 0 || index >= cascade.traces.length) return null;
        return cascade.traces[index].captureNumber;
      };
      instance.on("mouseover", (params) => {
        hoveredCaptureRef.current = captureOf(params as SeriesEventParams);
      });
      instance.on("mouseout", () => {
        hoveredCaptureRef.current = null;
      });
      instance.on("click", (params) => {
        const captureNumber = captureOf(params as SeriesEventParams);
        if (captureNumber !== null) setSelectedCaptureNumber(captureNumber);
      });
    },
    [cascade.traces]
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
    setSelectedCaptureNumber(newestCaptureNumber);
  }, [getInstance, newestCaptureNumber]);

  const handleCrosshair = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    const next = !crosshairEnabled;
    setCrosshairEnabledState(next);
    setCrosshairEnabled(instance, next);
  }, [crosshairEnabled, getInstance]);

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    const dataUrl = instance.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#FFFDF8",
    });
    const link = document.createElement("a");
    link.download = `sensovibe-cascade-ch${meta.channel + 1}-${cascade.traces.length}captures.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, meta.channel, cascade.traces.length]);

  const facts = headerFacts(meta, cascade.traces.length);
  const modeLabel = WATERFALL_MODE_LABELS[meta.selection_mode] ?? meta.selection_mode;
  const amplitudeUnit = meta.z_label.match(/\(([^)]+)\)/)?.[1] ?? "";

  return (
    <GraphWorkspace
      title="2D FFT Cascade"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>Frequency (Hz) · stacked FFT traces</span>
          <span aria-hidden>·</span>
          <strong className="text-brand">{cascade.traces.length}</strong>
          <span>of {meta.total_available} captures</span>
          <span aria-hidden>·</span>
          <span>{modeLabel}</span>
          <span aria-hidden>·</span>
          <span>stacked oldest→newest</span>
        </span>
      }
      headerExtra={
        <div className="flex flex-wrap items-center gap-1.5">
          {facts.map((fact) => (
            <span
              key={fact}
              className={cn(
                "rounded border border-border bg-warm/40 px-1.5 py-0.5",
                "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
              )}
            >
              {fact}
            </span>
          ))}
        </div>
      }
      height={height}
      variant="primary"
      hint="Click a trace to highlight it · Scroll to zoom frequency · Drag the slider to pan · Y axis is capture stacking offset, not amplitude"
      statistics={
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">
            {meta.x_label}: {formatHz(cascade.frequencyRange[0])} –{" "}
            {formatHz(cascade.frequencyRange[1])} ·{" "}
            {cascade.totalPoints.toLocaleString()} plotted bins · {cascade.peaks.length} peak
            markers · full-scale trace = {cascade.amplitudeMax.toExponential(2)}
            {amplitudeUnit ? ` ${amplitudeUnit}` : ""}
          </p>
          {selectedTrace && (
            <p className="text-[11px] text-muted-foreground">
              Highlighted: <strong className="text-brand">Capture #{selectedTrace.captureNumber}</strong>
              {" · "}
              {new Date(selectedTrace.capturedAt).toLocaleString()}
              {selectedTrace.peaks.length > 0 && ` · ${selectedTrace.peaks.length} peaks`}
              {shaftSpeed.rpm != null &&
                ` · Estimated shaft speed ${Math.round(shaftSpeed.rpm).toLocaleString()} RPM (estimated from FFT, not measured)`}
            </p>
          )}
          {!cascade.isReadable && (
            <p className="text-[11px] text-signal-dark">
              Traces are only {cascade.lanePx.toFixed(1)}px apart — reduce the capture count
              or open fullscreen for a clearer cascade.
            </p>
          )}
        </div>
      }
      onZoomIn={handleZoomIn}
      onZoomOut={handleZoomOut}
      onReset={handleReset}
      onCrosshair={handleCrosshair}
      onToggleThresholds={() => setShowPeaks((value) => !value)}
      onAutoscale={() => {
        const instance = getInstance();
        if (instance) autoscaleChart(instance);
      }}
      onExport={handleExport}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      onChartResize={handleResize}
      isCrosshairActive={crosshairEnabled}
      thresholdsVisible={showPeaks}
      channelLabel={`CH-${meta.channel + 1}`}
      toolbarActions={[
        "zoomIn",
        "zoomOut",
        "reset",
        "crosshair",
        "thresholds",
        "autoscale",
        "refresh",
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
          onChartReady={handleChartReady}
          // Per-trace widths encode the highlighted capture — a uniform width would erase it.
          adaptiveLineWidth={false}
        />
      )}
    </GraphWorkspace>
  );
}

export const FFTCascadePlot = memo(FFTCascadePlotInner);

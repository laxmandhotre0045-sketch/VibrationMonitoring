import React, { memo, useCallback, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import {
  buildPolarVectorChartOption,
  buildPolarVectorTooltip,
  formatAmplitudeValue,
  formatPhase,
} from "@/lib/polar-vector-option";
import type { PolarVectorModel } from "@/lib/polar-vector-transform";
import type { VibrationVectorResponse } from "@/types/vector";
import { cn } from "@/lib/utils";

const ZOOM_STEP = 1.4;

interface PolarVectorPlotProps {
  model: PolarVectorModel;
  meta: VibrationVectorResponse;
  height: number;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

function headerFacts(meta: VibrationVectorResponse): string[] {
  const facts = [`CH ${meta.channel + 1}`];
  if (meta.orientation) facts.push(meta.orientation.toUpperCase());
  if (meta.window) facts.push(meta.window);
  facts.push(`${meta.block_size.toLocaleString()}-pt`);
  facts.push(`${meta.block_count} block${meta.block_count === 1 ? "" : "s"}`);
  facts.push(`Δf ${meta.frequency_resolution_hz.toFixed(2)} Hz`);
  return facts;
}

function PolarVectorPlotInner({
  model,
  meta,
  height,
  onRefresh,
  isRefreshing = false,
}: PolarVectorPlotProps) {
  const chartRef = useRef<ReactECharts>(null);
  const radiusScaleRef = useRef(1);
  const [showPath, setShowPath] = useState(true);

  const tooltipFormatter = useMemo(
    () => buildPolarVectorTooltip({ model, meta }),
    [model, meta]
  );

  // Rebuilt only on data/label change — zoom is applied imperatively below.
  const option = useMemo(
    () => buildPolarVectorChartOption({ model, meta, showPath, tooltipFormatter }),
    [model, meta, showPath, tooltipFormatter]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  /** Zoom the radial (amplitude) scale — the meaningful zoom on a centred polar plot. */
  const applyRadius = useCallback(
    (scale: number) => {
      const instance = getInstance();
      if (!instance || instance.isDisposed()) return;
      radiusScaleRef.current = Math.min(8, Math.max(0.05, scale));
      instance.setOption(
        { radiusAxis: { max: model.radiusMax * radiusScaleRef.current } },
        false
      );
    },
    [getInstance, model.radiusMax]
  );

  const handleReset = useCallback(() => applyRadius(1), [applyRadius]);
  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) instance.resize();
  }, [getInstance]);

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    const dataUrl = instance.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#FFFDF8",
    });
    const link = document.createElement("a");
    link.download = `sensovibe-vector-ch${meta.channel + 1}-${meta.bin_hz.toFixed(1)}Hz.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, meta.channel, meta.bin_hz]);

  const facts = headerFacts(meta);
  const latest = model.latest;
  const drift = meta.drift;

  return (
    <GraphWorkspace
      title="Vibration Vector"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <strong className="text-brand">{meta.target_label}</strong>
          <span aria-hidden>·</span>
          <span>
            FFT bin {meta.bin_hz.toFixed(2)} Hz (#{meta.bin_index})
          </span>
          <span aria-hidden>·</span>
          <span>Self-referenced phase · amplitude in {model.amplitudeUnit || "—"}</span>
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
      hint="Phase: 0° at 3 o'clock, positive counter-clockwise · colour runs light (first block) → dark (latest) · zoom scales the amplitude axis"
      statistics={
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">
            Amplitude {formatAmplitudeValue(meta.amplitude_min, model.amplitudeUnit)} –{" "}
            {formatAmplitudeValue(meta.amplitude_max, model.amplitudeUnit)}
            {latest && (
              <>
                {" · "}Latest: {formatAmplitudeValue(latest.amplitude, model.amplitudeUnit)} at{" "}
                {formatPhase(latest.relativePhaseDeg)}
              </>
            )}
            {model.estimatedRpm != null && (
              <> · Estimated shaft speed {Math.round(model.estimatedRpm).toLocaleString()} RPM (estimated from FFT, not measured)</>
            )}
          </p>
          <p className="text-[11px] text-muted-foreground">
            Phase is self-referenced to the first analysis block; absolute shaft phase requires a keyphasor.
          </p>
          {drift.likely_bin_mismatch && drift.implied_frequency_offset_hz != null && (
            <p className="text-[11px] text-signal-dark">
              Possible frequency-bin drift: phase changes nearly linearly (
              {drift.phase_slope_deg_per_s?.toFixed(0)}°/s) while amplitude stays stable, implying the
              signal sits about {drift.implied_frequency_offset_hz.toFixed(2)} Hz from the selected bin.
              A smooth sweep like this can indicate bin mismatch rather than a machine change.
            </p>
          )}
        </div>
      }
      onZoomIn={() => applyRadius(radiusScaleRef.current / ZOOM_STEP)}
      onZoomOut={() => applyRadius(radiusScaleRef.current * ZOOM_STEP)}
      onReset={handleReset}
      onAutoscale={handleReset}
      onToggleThresholds={() => setShowPath((v) => !v)}
      onExport={handleExport}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      onChartResize={handleResize}
      thresholdsVisible={showPath}
      channelLabel={`CH-${meta.channel + 1}`}
      toolbarActions={[
        "zoomIn",
        "zoomOut",
        "reset",
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
          // Polar has no dataZoom, and the uniform line-width helper would flatten the
          // current-vector emphasis.
          adaptiveLineWidth={false}
        />
      )}
    </GraphWorkspace>
  );
}

export const PolarVectorPlot = memo(PolarVectorPlotInner);

import React, { memo, useCallback, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { GraphWorkspace } from "@/components/charts";
import { Echarts3DViewport } from "@/components/charts/Echarts3DViewport";
import {
  buildWaterfall3DOption,
  CAMERA_MAX_DISTANCE,
  CAMERA_MIN_DISTANCE,
  DEFAULT_WATERFALL_CAMERA,
} from "@/lib/waterfall-3d-option";
import type { WaterfallModel } from "@/lib/waterfall-adapter";
import { WATERFALL_MODE_LABELS, type WaterfallResponse } from "@/types/waterfall";
import { cn } from "@/lib/utils";

const ZOOM_STEP = 1.25;

interface FFTWaterfall3DProps {
  model: WaterfallModel;
  meta: WaterfallResponse;
  height: number;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

function formatHz(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value >= 1000) return `${Math.round(value).toLocaleString()} Hz`;
  return `${value.toFixed(value >= 10 ? 0 : 2)} Hz`;
}

/** Only render the parts we actually have — never print "undefined" in the header. */
function headerFacts(meta: WaterfallResponse, model: WaterfallModel): string[] {
  const facts: string[] = [`CH ${meta.channel + 1}`];
  if (meta.orientation) facts.push(meta.orientation.toUpperCase());
  if (meta.window) facts.push(meta.window);
  if (meta.fft_lines) facts.push(`${meta.fft_lines.toLocaleString()}-pt`);
  facts.push(`${model.lines.length} capture${model.lines.length === 1 ? "" : "s"}`);
  if (meta.frequency_resolution_hz) facts.push(`Δf ${formatHz(meta.frequency_resolution_hz)}`);
  return facts;
}

function FFTWaterfall3DInner({
  model,
  meta,
  height,
  onRefresh,
  isRefreshing = false,
}: FFTWaterfall3DProps) {
  const chartRef = useRef<ReactECharts>(null);
  const distanceRef = useRef(DEFAULT_WATERFALL_CAMERA.distance);

  // Rebuilt only when the data or labels change — camera moves never touch this.
  const option = useMemo(
    () => buildWaterfall3DOption({ model, meta }),
    [model, meta]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  /** Camera is driven by merging viewControl only, so the scene is never rebuilt. */
  const applyCamera = useCallback(
    (camera: Partial<typeof DEFAULT_WATERFALL_CAMERA>) => {
      const instance = getInstance();
      if (!instance || instance.isDisposed()) return;
      instance.setOption({ grid3D: { viewControl: camera } }, false);
    },
    [getInstance]
  );

  const zoomBy = useCallback(
    (factor: number) => {
      const next = Math.min(
        CAMERA_MAX_DISTANCE,
        Math.max(CAMERA_MIN_DISTANCE, distanceRef.current * factor)
      );
      distanceRef.current = next;
      applyCamera({ distance: next });
    },
    [applyCamera]
  );

  const handleReset = useCallback(() => {
    distanceRef.current = DEFAULT_WATERFALL_CAMERA.distance;
    applyCamera(DEFAULT_WATERFALL_CAMERA);
  }, [applyCamera]);

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) instance.resize();
  }, [getInstance]);

  const handleExportPng = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    try {
      const dataUrl = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#FFFFFF" });
      if (!dataUrl || dataUrl.length < 100) return;
      const link = document.createElement("a");
      link.download = `sensovibe-waterfall-ch${meta.channel + 1}-${model.lines.length}captures.png`;
      link.href = dataUrl;
      link.click();
    } catch {
      // WebGL snapshot unavailable in this browser — the CSV export still has the data.
    }
  }, [getInstance, meta.channel, model.lines.length]);

  const facts = headerFacts(meta, model);
  const modeLabel = WATERFALL_MODE_LABELS[meta.selection_mode] ?? meta.selection_mode;

  const subtitle = (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      <strong className="text-brand">{model.lines.length}</strong>
      <span>of {meta.total_available} captures</span>
      <span aria-hidden>·</span>
      <span>{modeLabel}</span>
      <span aria-hidden>·</span>
      <span>stacked oldest→newest</span>
      {meta.skipped_count > 0 && (
        <>
          <span aria-hidden>·</span>
          <span className="text-signal-dark font-medium">{meta.skipped_count} skipped</span>
        </>
      )}
    </span>
  );

  const headerExtra = (
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
  );

  return (
    <GraphWorkspace
      title="3D FFT Waterfall"
      subtitle={subtitle}
      headerExtra={headerExtra}
      height={height}
      variant="primary"
      hint="Drag to rotate · Scroll to zoom · Middle-drag to pan · Reset restores the default view"
      statistics={
        <p className="text-[11px] text-muted-foreground">
          {meta.x_label}: {formatHz(meta.frequency_min_hz)} – {formatHz(meta.frequency_max_hz)} ·{" "}
          {model.totalPoints.toLocaleString()} plotted bins · {model.peaks.length} peak markers
          {model.droppedPoints > 0 && ` · ${model.droppedPoints} invalid bins dropped`}
        </p>
      }
      onZoomIn={() => zoomBy(1 / ZOOM_STEP)}
      onZoomOut={() => zoomBy(ZOOM_STEP)}
      onReset={handleReset}
      onExport={handleExportPng}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      onChartResize={handleResize}
      channelLabel={`CH-${meta.channel + 1}`}
      toolbarActions={["zoomIn", "zoomOut", "reset", "refresh", "export", "fullscreen"]}
    >
      {({ height: chartHeight, isFullscreen }) => (
        <Echarts3DViewport
          chartRef={chartRef}
          option={option}
          chartHeight={chartHeight}
          isFullscreen={isFullscreen}
        />
      )}
    </GraphWorkspace>
  );
}

export const FFTWaterfall3D = memo(FFTWaterfall3DInner);

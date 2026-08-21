import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import {
  buildOrbitChartOption,
  buildOrbitTooltip,
  enforceEqualScale,
  formatMicrons,
  orbitRange,
} from "@/lib/orbit-plot-option";
import type { CasingOrbitResponse } from "@/types/orbit";
import { cn } from "@/lib/utils";

interface CasingOrbitPlotProps {
  data: CasingOrbitResponse;
  height: number;
  showUnfiltered: boolean;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

function headerFacts(d: CasingOrbitResponse): string[] {
  const facts = [`X ch${d.x_channel}`, `Y ch${d.y_channel}`, `${d.harmonic}×`];
  facts.push(`${d.centre_hz.toFixed(1)} Hz`);
  facts.push(`filter ${d.filter_revolutions} rev`);
  facts.push(`show ${d.display_revolutions} rev`);
  return facts;
}

function CasingOrbitPlotInner({
  data,
  height,
  showUnfiltered,
  onRefresh,
  isRefreshing = false,
}: CasingOrbitPlotProps) {
  const chartRef = useRef<ReactECharts>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [boxSize, setBoxSize] = useState(Math.min(height, 560));

  // The plot box must be square for equal physical scale, so it is sized from the
  // smaller of the available width and height.
  useEffect(() => {
    const measure = () => {
      const width = boxRef.current?.clientWidth ?? height;
      setBoxSize(Math.max(240, Math.min(width, height)));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    if (boxRef.current) observer.observe(boxRef.current);
    return () => observer.disconnect();
  }, [height]);

  const tooltipFormatter = useMemo(() => buildOrbitTooltip(data), [data]);
  const option = useMemo(
    () => buildOrbitChartOption({ data, boxSize, showUnfiltered, tooltipFormatter }),
    [data, boxSize, showUnfiltered, tooltipFormatter]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  /** Correct the axis ranges to the grid ECharts actually laid out, so scale is 1:1. */
  const applyEqualScale = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) {
      enforceEqualScale(instance as never, orbitRange(data));
    }
  }, [getInstance, data]);

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) {
      instance.resize();
      applyEqualScale();
    }
  }, [getInstance, applyEqualScale]);

  // Re-assert after every option rebuild — setOption resets the ranges to the base value.
  //
  // The viewport renders with lazyUpdate, so the model does not exist on the effect tick.
  // Retry across a frame and a short timeout; every call is a no-op until the grid is laid
  // out, and the ECharts "finished" handler below covers the rest.
  useEffect(() => {
    applyEqualScale();
    const frame = requestAnimationFrame(applyEqualScale);
    const timer = window.setTimeout(applyEqualScale, 120);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [applyEqualScale, option]);

  const handleChartReady = useCallback(
    (instance: EChartsType) => {
      instance.on("finished", applyEqualScale);
      applyEqualScale();
    },
    [applyEqualScale]
  );

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    const dataUrl = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#FFFDF8" });
    const link = document.createElement("a");
    link.download = `sensovibe-orbit-ch${data.x_channel}-ch${data.y_channel}-${data.harmonic}x.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, data.x_channel, data.y_channel, data.harmonic]);

  const rpm = data.estimated_shaft_hz != null ? Math.round(data.estimated_shaft_hz * 60) : null;

  return (
    <GraphWorkspace
      title="Casing Orbit"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>
            ch{data.x_channel} → X · ch{data.y_channel} → Y
          </span>
          <span aria-hidden>·</span>
          <strong className="text-brand">
            {data.harmonic}× · {data.centre_hz.toFixed(1)} Hz
          </strong>
          {rpm != null && (
            <>
              <span aria-hidden>·</span>
              <span>Estimated shaft speed {rpm.toLocaleString()} RPM</span>
            </>
          )}
        </span>
      }
      headerExtra={
        <div className="flex flex-wrap items-center gap-1.5">
          {headerFacts(data).map((f) => (
            <span
              key={f}
              className={cn(
                "rounded border border-border bg-warm/40 px-1.5 py-0.5",
                "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
              )}
            >
              {f}
            </span>
          ))}
        </div>
      }
      height={height}
      variant="primary"
      hint="Accelerometer-based casing motion · double-integrated displacement · X and Y share one scale (1:1)"
      statistics={
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">
            Peak {formatMicrons(data.peak_displacement_um)} {data.amplitude_unit} · band{" "}
            {data.lower_hz.toFixed(2)}–{data.upper_hz.toFixed(2)} Hz · Δf{" "}
            {data.frequency_resolution_hz.toFixed(2)} Hz · filtered over{" "}
            {data.filter_duration_s.toFixed(3)} s, showing {data.display_duration_s.toFixed(3)} s
            from the middle · {data.point_count} points · Colour = time progression
          </p>
          <p className="text-[11px] text-muted-foreground">
            Casing orbit from accelerometers — not a shaft-centreline proximity-probe orbit.
            Direction shown is time progression; absolute shaft rotation direction requires a
            keyphasor, which this system does not have.
          </p>
        </div>
      }
      onReset={handleResize}
      onExport={handleExport}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      onChartResize={handleResize}
      channelLabel={`ch${data.x_channel}/ch${data.y_channel}`}
      toolbarActions={["reset", "refresh", "export", "fullscreen"]}
    >
      {({ height: chartHeight, isFullscreen }) => (
        <div ref={boxRef} className="flex h-full w-full items-center justify-center">
          <div style={{ width: boxSize, height: Math.min(boxSize, chartHeight) }}>
            <EchartsGraphViewport
              chartRef={chartRef}
              option={option}
              chartHeight={Math.min(boxSize, chartHeight)}
              isFullscreen={isFullscreen}
              onChartReady={handleChartReady}
              adaptiveLineWidth={false}
            />
          </div>
        </div>
      )}
    </GraphWorkspace>
  );
}

export const CasingOrbitPlot = memo(CasingOrbitPlotInner);

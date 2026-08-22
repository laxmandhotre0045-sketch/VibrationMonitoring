import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import { enforceEqualScale } from "@/lib/orbit-plot-option";
import {
  buildMigrationChartOption,
  buildMigrationTooltip,
  formatAmplitude,
  migrationAxisMax,
} from "@/lib/migration-plot-option";
import type { OneXMigrationResponse } from "@/types/migration";
import { cn } from "@/lib/utils";

interface OneXMigrationPlotProps {
  data: OneXMigrationResponse;
  height: number;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

function headerFacts(d: OneXMigrationResponse): string[] {
  const facts = [`X ch${d.x_channel}`, `Y ch${d.y_channel}`, "1×"];
  facts.push(`${d.summary.valid_count} of ${d.returned_count} valid`);
  if (d.summary.shaft_hz_min != null && d.summary.shaft_hz_max != null) {
    facts.push(
      d.summary.shaft_hz_min === d.summary.shaft_hz_max
        ? `${d.summary.shaft_hz_min.toPrecision(4)} Hz`
        : `${d.summary.shaft_hz_min.toPrecision(3)}–${d.summary.shaft_hz_max.toPrecision(3)} Hz`
    );
  }
  return facts;
}

function OneXMigrationPlotInner({
  data,
  height,
  onRefresh,
  isRefreshing = false,
}: OneXMigrationPlotProps) {
  const chartRef = useRef<ReactECharts>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [boxSize, setBoxSize] = useState(Math.min(height, 560));

  // Square plot box: equal physical scale on both axes is mandatory here.
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

  const tooltipFormatter = useMemo(() => buildMigrationTooltip(data), [data]);
  const option = useMemo(
    () => buildMigrationChartOption({ data, boxSize, tooltipFormatter }),
    [data, boxSize, tooltipFormatter]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  /**
   * Same correction the orbit uses: measure the grid ECharts actually laid out and widen
   * the axis ranges so px-per-micrometre matches. Both axes start at 0 here, so the
   * helper's symmetric range is re-mapped to [0, span] below.
   */
  const applyEqualScale = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    const result = enforceEqualScale(instance as never, migrationAxisMax(data) / 2);
    if (result) {
      instance.setOption(
        { xAxis: { min: 0, max: result.rx * 2 }, yAxis: { min: 0, max: result.ry * 2 } },
        false
      );
    }
  }, [getInstance, data]);

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

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) {
      instance.resize();
      applyEqualScale();
    }
  }, [getInstance, applyEqualScale]);

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance || instance.isDisposed()) return;
    const url = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#FFFDF8" });
    const link = document.createElement("a");
    link.download = `sensovibe-1x-migration-ch${data.x_channel}-ch${data.y_channel}.png`;
    link.href = url;
    link.click();
  }, [getInstance, data.x_channel, data.y_channel]);

  const valid = data.points.filter((p) => p.quality !== "invalid");
  const latest = valid[valid.length - 1];
  const unit = data.amplitude_unit;

  return (
    <GraphWorkspace
      title="1× Amplitude Migration"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>Vertical vs Horizontal 1× casing vibration response</span>
          <span aria-hidden>·</span>
          <strong className="text-brand">{data.summary.valid_count} captures</strong>
          <span aria-hidden>·</span>
          <span>oldest → newest</span>
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
      hint="One point per capture · ○ Start ◆ Latest · colour = capture time · X and Y share one scale (1:1)"
      statistics={
        <div className="space-y-1">
          {latest && (
            <p className="text-[11px] text-muted-foreground">
              Latest — Vertical {formatAmplitude(latest.x_amplitude, unit)} · Horizontal{" "}
              {formatAmplitude(latest.y_amplitude, unit)} · vector{" "}
              {formatAmplitude(latest.vector_amplitude, unit)}
              {latest.vh_ratio != null && <> · V/H {latest.vh_ratio.toPrecision(3)}</>}
              {latest.relative_phase_deg != null && (
                <> · relative V-H phase {latest.relative_phase_deg > 0 ? "+" : ""}
                  {latest.relative_phase_deg.toFixed(1)}°</>
              )}
              {latest.shaft_rpm != null && (
                <> · estimated shaft speed {Math.round(latest.shaft_rpm).toLocaleString()} RPM</>
              )}
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            Accelerometer-based 1× casing vibration response. This is not a static
            shaft-centreline measurement; true shaft centreline requires DC-capable proximity
            probes. Amplitudes are magnitudes, so the plot occupies the positive quadrant.
          </p>
          <p className="text-[11px] text-muted-foreground">
            Sub-micron accelerometer-derived displacement should be read as a relative response
            trend; casing severity is normally judged on velocity-based metrics.
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

export const OneXMigrationPlot = memo(OneXMigrationPlotInner);

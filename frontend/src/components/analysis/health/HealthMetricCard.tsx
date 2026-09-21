import React, { useCallback, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { Info } from "lucide-react";
import type { HealthMetricTrend } from "@/types/health-status";
import { MetricInsightModal } from "@/components/analysis/health/MetricInsightModal";
import { buildHealthTrendOption, formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { GRAPH_KPI_CARD_HEIGHT } from "@/lib/chart-constants";
import { resetChartZoom } from "@/lib/graph-interactions";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import { cn } from "@/lib/utils";

interface HealthMetricCardProps {
  metric: HealthMetricTrend;
  channelLabel: string;
  className?: string;
}

const STATUS_STYLES = {
  healthy: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/30",
  warning: "bg-signal-light/15 text-signal-dark border-signal-light/45",
  danger: "bg-destructive/10 text-destructive border-destructive/30",
  neutral: "bg-muted/40 text-muted-foreground border-border",
} as const;

const STATUS_DOTS = {
  healthy: "bg-machine-healthy",
  warning: "bg-signal-light",
  danger: "bg-destructive",
  neutral: "bg-muted-foreground/50",
} as const;

const STATUS_LABELS = {
  healthy: "OK",
  warning: "Warning",
  danger: "Danger",
  neutral: "Trend",
} as const;

/**
 * Three controls, not eight.
 *
 * Zoom in/out, pan, crosshair and refresh all duplicated something the chart
 * already does on its own — the wheel and the time-range slider zoom, drag
 * pans, the crosshair is on, and the query refetches itself. Ten cards times
 * eight buttons was eighty icons of chrome competing with the traces they sit
 * above. What is left is what has no other trigger: undo a zoom, save a PNG,
 * open it large.
 */
const KPI_TOOLBAR_ACTIONS = ["reset", "export", "fullscreen"] as const;

/**
 * KPI heading, the way an instrument panel writes it: "RMS (scaled)".
 *
 * The trend series arrive labelled "<Feature> Trend" because that is what they
 * are in a list of series. On a card inside a section already titled "Feature
 * Trend Monitoring" the suffix is repeated furniture, and it pushes the unit —
 * the part a reader needs to interpret the number under it — out of sight.
 */
function metricHeading(metric: HealthMetricTrend): { name: string; unit: string } {
  return { name: metric.label.replace(/\s+Trend$/i, ""), unit: metric.unit };
}

export function HealthMetricCard({ metric, channelLabel, className }: HealthMetricCardProps) {
  const chartRef = useRef<ReactECharts>(null);
  const [insightOpen, setInsightOpen] = useState(false);

  const option = useMemo(
    () => buildHealthTrendOption(metric, channelLabel),
    [metric, channelLabel]
  );

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) instance.resize();
  }, [getInstance]);

  const handleReset = useCallback(() => {
    const instance = getInstance();
    if (instance) resetChartZoom(instance);
  }, [getInstance]);

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

  const heading = metricHeading(metric);

  const headerExtra = (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1",
          "text-[11px] font-bold uppercase tracking-[0.08em]",
          STATUS_STYLES[metric.status]
        )}
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOTS[metric.status])} aria-hidden />
        {STATUS_LABELS[metric.status]}
      </span>

      {/* Sits with the status badge because it explains it: the badge says
          which side of the limit the reading fell, this says why and what to
          do next. */}
      <button
        type="button"
        onClick={() => setInsightOpen(true)}
        title={`AI reading for ${heading.name}`}
        aria-label={`AI reading for ${heading.name}`}
        className={cn(
          // Same 32px box as the toolbar buttons beside it, so the header reads
          // as one row of controls rather than two sizes of button.
          "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
          "border-signal-light/45 bg-signal-light/10 text-signal-dark transition-colors",
          "hover:border-signal-light hover:bg-signal-light/20",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]"
        )}
      >
        <Info size={14} strokeWidth={2.5} aria-hidden />
      </button>
    </span>
  );

  // Title and unit read as one line — "RMS (scaled)" — with the unit set back
  // so the metric name carries the weight.
  const titleNode = (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="text-base font-bold text-foreground">{heading.name}</span>
      {heading.unit && (
        <span className="text-sm font-medium text-muted-foreground">({heading.unit})</span>
      )}
    </span>
  );

  // The reading itself is the headline of a KPI card — the same number the
  // status badge beside it was judged on, straight from the metric.
  const subtitle = (
    <span className="block text-xl font-bold leading-tight text-foreground tabular-nums">
      {metric.available ? formatHealthMetricDisplay(metric.value, metric.unit) : "N/A"}
    </span>
  );

  return (
    <>
      <MetricInsightModal
        open={insightOpen}
        metric={metric}
        channelLabel={channelLabel}
        onClose={() => setInsightOpen(false)}
      />
      <GraphWorkspace
        className={cn("h-full", className)}
        variant="primary"
        height={GRAPH_KPI_CARD_HEIGHT}
        title={heading.unit ? `${heading.name} (${heading.unit})` : heading.name}
        titleNode={titleNode}
        subtitle={subtitle}
        headerExtra={headerExtra}
        toolbarPlacement="header"
        statistics={
          <p className="text-center text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Time Range
          </p>
        }
        onReset={metric.available ? handleReset : undefined}
        onExport={metric.available ? handleExport : undefined}
        onChartResize={handleResize}
        toolbarActions={[...KPI_TOOLBAR_ACTIONS]}
      >
        {({ height: chartHeight, isFullscreen }) =>
          metric.available ? (
            <EchartsGraphViewport
              chartRef={chartRef}
              option={option}
              chartHeight={chartHeight}
              isFullscreen={isFullscreen}
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
    </>
  );
}

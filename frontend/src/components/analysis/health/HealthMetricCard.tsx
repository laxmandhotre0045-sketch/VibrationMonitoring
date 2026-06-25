import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { Download, Expand, Minimize2, RefreshCw } from "lucide-react";
import type { HealthMetricTrend } from "@/types/health-status";
import { buildHealthTrendOption, formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { computeFullscreenChartHeight } from "@/lib/chart-layout";
import { useEchartsResize } from "@/hooks/useEchartsResize";
import { cn } from "@/lib/utils";

const HEALTH_CARD_CHART_HEIGHT = 168;

interface HealthMetricCardProps {
  metric: HealthMetricTrend;
  channelLabel: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
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

function ActionButton({
  onClick,
  title,
  disabled,
  children,
}: {
  onClick?: () => void;
  title: string;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || !onClick}
      className={cn(
        "rounded-md p-1.5 transition-colors",
        "text-muted-foreground hover:bg-warm hover:text-foreground",
        "disabled:opacity-40 disabled:cursor-not-allowed"
      )}
    >
      {children}
    </button>
  );
}

export function HealthMetricCard({
  metric,
  channelLabel,
  onRefresh,
  isRefreshing = false,
  className,
}: HealthMetricCardProps) {
  const shellRef = useRef<HTMLDivElement>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReactECharts>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [usePortalFallback, setUsePortalFallback] = useState(false);
  const [measuredHeight, setMeasuredHeight] = useState(HEALTH_CARD_CHART_HEIGHT);

  const option = useMemo(() => buildHealthTrendOption(metric), [metric]);

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) instance.resize();
  }, [getInstance]);

  useEchartsResize(getInstance, [option, isFullscreen, measuredHeight]);

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

  const handleToggleFullscreen = useCallback(async () => {
    const el = shellRef.current;
    if (!el) return;

    if (usePortalFallback) {
      setUsePortalFallback(false);
      document.body.style.overflow = "";
      handleResize();
      return;
    }

    if (document.fullscreenElement === el) {
      await document.exitFullscreen();
      return;
    }

    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      await el.requestFullscreen();
    } catch {
      setUsePortalFallback(true);
      document.body.style.overflow = "hidden";
      handleResize();
    }
  }, [handleResize, usePortalFallback]);

  useEffect(() => {
    const onFullscreenChange = () => {
      const el = shellRef.current;
      const nativeActive = !!el && document.fullscreenElement === el;
      setIsFullscreen(nativeActive || usePortalFallback);
      if (!nativeActive && !usePortalFallback) document.body.style.overflow = "";
      handleResize();
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [handleResize, usePortalFallback]);

  useEffect(() => {
    if (!usePortalFallback) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setUsePortalFallback(false);
        document.body.style.overflow = "";
        handleResize();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [usePortalFallback, handleResize]);

  useLayoutEffect(() => {
    if (!isFullscreen && !usePortalFallback) {
      setMeasuredHeight(HEALTH_CARD_CHART_HEIGHT);
      return;
    }
    const area = chartAreaRef.current;
    if (!area) return;
    const next = Math.max(area.clientHeight, computeFullscreenChartHeight());
    if (next > 0) setMeasuredHeight(next);
  }, [isFullscreen, usePortalFallback]);

  const isExpanded = isFullscreen || usePortalFallback;
  const chartHeight = isExpanded ? measuredHeight : HEALTH_CARD_CHART_HEIGHT;

  const shell = (
    <div
      ref={shellRef}
      className={cn(
        "health-metric-card flex h-full min-h-[260px] flex-col rounded-lg border border-border border-l-2 border-l-signal-light bg-white p-3",
        isExpanded && usePortalFallback &&
          "fixed inset-0 z-[200] m-0 min-h-0 rounded-none border-0 p-4 sm:p-6",
        isExpanded && !usePortalFallback && "flex flex-col",
        className
      )}
      role={isExpanded ? "dialog" : undefined}
      aria-modal={isExpanded ? true : undefined}
      aria-label={isExpanded ? `${metric.label} fullscreen view` : undefined}
    >
      <div className="mb-2 flex shrink-0 items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-foreground truncate">{metric.label}</h3>
            {metric.unit && (
              <span className="text-xs text-muted-foreground">({metric.unit})</span>
            )}
            <span
              className={cn(
                "inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold",
                STATUS_STYLES[metric.status]
              )}
            >
              {STATUS_LABELS[metric.status]}
            </span>
          </div>
          <p className="mt-1 text-xl font-bold text-brand leading-tight">
            {metric.available
              ? formatHealthMetricDisplay(metric.value, metric.unit)
              : "N/A"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-0.5 rounded-md bg-white/95">
          <ActionButton
            onClick={onRefresh}
            title="Refresh"
            disabled={isRefreshing}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
          </ActionButton>
          <ActionButton onClick={handleExport} title="Export image (PNG)" disabled={!metric.available}>
            <Download className="h-3.5 w-3.5" />
          </ActionButton>
          <ActionButton
            onClick={handleToggleFullscreen}
            title={isExpanded ? "Exit fullscreen" : "Fullscreen"}
            disabled={!metric.available}
          >
            {isExpanded ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Expand className="h-3.5 w-3.5" />
            )}
          </ActionButton>
        </div>
      </div>

      <div
        ref={chartAreaRef}
        className={cn(
          "relative w-full min-w-0 flex-1",
          isExpanded ? "min-h-0" : "overflow-hidden"
        )}
        style={isExpanded ? { minHeight: chartHeight } : { height: chartHeight }}
      >
        {metric.available ? (
          <ReactECharts
            ref={chartRef}
            option={option}
            notMerge
            lazyUpdate
            style={{ width: "100%", height: chartHeight }}
            opts={{ renderer: "canvas" }}
          />
        ) : (
          <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border bg-surface/40 px-3">
            <p className="text-sm text-muted-foreground text-center">
              Not available for this capture
            </p>
          </div>
        )}
      </div>

      <div className="mt-2 flex shrink-0 items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{channelLabel}</span>
        <span>Segment trend</span>
      </div>
    </div>
  );

  if (usePortalFallback) return createPortal(shell, document.body);
  return shell;
}

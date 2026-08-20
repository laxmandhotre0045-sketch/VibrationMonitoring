import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GRAPH_PRIMARY_HEIGHT } from "@/lib/chart-constants";
import { computeFullscreenChartHeight } from "@/lib/chart-layout";
import { cn } from "@/lib/utils";
import { GraphToolbar, type GraphToolbarAction } from "./GraphToolbar";

function scheduleChartResize(callback?: () => void) {
  callback?.();
  requestAnimationFrame(() => callback?.());
  window.setTimeout(() => callback?.(), 100);
  window.setTimeout(() => callback?.(), 300);
}

export type GraphWorkspaceVariant = "primary" | "compact";

interface GraphWorkspaceProps {
  title?: string;
  subtitle?: React.ReactNode;
  height?: number;
  variant?: GraphWorkspaceVariant;
  hint?: string;
  controls?: React.ReactNode;
  headerExtra?: React.ReactNode;
  statistics?: React.ReactNode;
  toolbarActions?: GraphToolbarAction[];
  channelLabel?: string;
  channelSlot?: React.ReactNode;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onPan?: () => void;
  onReset?: () => void;
  onCrosshair?: () => void;
  onToggleThresholds?: () => void;
  onFullscreen?: () => void;
  onExport?: () => void;
  onRefresh?: () => void;
  onAutoscale?: () => void;
  isCrosshairActive?: boolean;
  thresholdsVisible?: boolean;
  isRefreshing?: boolean;
  onChartResize?: () => void;
  manageFullscreen?: boolean;
  children: (props: { height: number; isFullscreen: boolean }) => React.ReactNode;
  className?: string;
}

export function GraphWorkspace({
  title,
  subtitle,
  height,
  variant = "primary",
  hint,
  controls,
  headerExtra,
  statistics,
  toolbarActions,
  channelLabel,
  channelSlot,
  onZoomIn,
  onZoomOut,
  onPan,
  onReset,
  onCrosshair,
  onToggleThresholds,
  onFullscreen: onFullscreenExternal,
  onExport,
  onRefresh,
  onAutoscale,
  isCrosshairActive = true,
  thresholdsVisible = true,
  isRefreshing = false,
  onChartResize,
  manageFullscreen = true,
  children,
  className,
}: GraphWorkspaceProps) {
  const resolvedHeight =
    height ?? (variant === "compact" ? 220 : GRAPH_PRIMARY_HEIGHT);

  const shellRef = useRef<HTMLDivElement>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [usePortalFallback, setUsePortalFallback] = useState(false);
  const [measuredChartHeight, setMeasuredChartHeight] = useState(resolvedHeight);

  const measureChartArea = useCallback(() => {
    const area = chartAreaRef.current;
    if (!area) return;
    const next = Math.max(area.clientHeight, 360);
    if (next > 0) setMeasuredChartHeight(next);
  }, []);

  const handleToggleFullscreen = useCallback(async () => {
    if (onFullscreenExternal) {
      onFullscreenExternal();
      return;
    }
    if (!manageFullscreen) return;

    const el = shellRef.current;
    if (!el) return;

    if (usePortalFallback) {
      setUsePortalFallback(false);
      document.body.style.overflow = "";
      scheduleChartResize(onChartResize);
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
      scheduleChartResize(onChartResize);
    }
  }, [manageFullscreen, onChartResize, onFullscreenExternal, usePortalFallback]);

  useEffect(() => {
    if (!manageFullscreen) return;

    const onFullscreenChange = () => {
      const el = shellRef.current;
      const nativeActive = !!el && document.fullscreenElement === el;
      setIsFullscreen(nativeActive || usePortalFallback);
      if (!nativeActive && !usePortalFallback) document.body.style.overflow = "";
      scheduleChartResize(onChartResize);
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [manageFullscreen, onChartResize, usePortalFallback]);

  useEffect(() => {
    if (!usePortalFallback) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setUsePortalFallback(false);
        document.body.style.overflow = "";
        scheduleChartResize(onChartResize);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [usePortalFallback, onChartResize]);

  useLayoutEffect(() => {
    if (!isFullscreen && !usePortalFallback) {
      setMeasuredChartHeight(resolvedHeight);
      return;
    }
    measureChartArea();
    scheduleChartResize(onChartResize);
    const area = chartAreaRef.current;
    if (!area || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      measureChartArea();
      onChartResize?.();
    });
    observer.observe(area);
    return () => observer.disconnect();
  }, [isFullscreen, usePortalFallback, resolvedHeight, measureChartArea, onChartResize]);

  const isExpanded = isFullscreen || usePortalFallback;
  const chartHeight = isExpanded
    ? Math.max(measuredChartHeight, computeFullscreenChartHeight())
    : resolvedHeight;

  const hasToolbar =
    toolbarActions?.length ||
    onZoomIn ||
    onZoomOut ||
    onReset ||
    onExport ||
    onRefresh ||
    onAutoscale ||
    onToggleThresholds ||
    manageFullscreen;

  const shell = (
    <div
      ref={shellRef}
      className={cn(
        "graph-workspace rounded-xl border border-border bg-white shadow-[0_2px_12px_rgba(21,54,109,0.06)]",
        variant === "primary" ? "p-3 sm:p-4" : "p-3",
        isExpanded && usePortalFallback &&
          "fixed inset-0 z-[200] m-0 flex h-dvh w-screen flex-col rounded-none border-0 p-g3 sm:p-g4",
        isExpanded && !usePortalFallback && "flex flex-col",
        className
      )}
      role={isExpanded ? "dialog" : undefined}
      aria-modal={isExpanded ? true : undefined}
      aria-label={isExpanded && title ? `${title} fullscreen view` : undefined}
    >
      {(title || subtitle || headerExtra) && (
        <div className="mb-g2 flex shrink-0 flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && (
              <h3 className="text-sm font-bold text-foreground leading-tight">{title}</h3>
            )}
            {subtitle && (
              <div className="mt-g1 text-xs text-muted-foreground">{subtitle}</div>
            )}
          </div>
          {headerExtra}
        </div>
      )}

      {controls && <div className="mb-g2 shrink-0">{controls}</div>}

      {hasToolbar && (
        <div className="mb-g2 shrink-0">
          <GraphToolbar
            actions={toolbarActions}
            onZoomIn={onZoomIn}
            onZoomOut={onZoomOut}
            onPan={onPan}
            onReset={onReset}
            onCrosshair={onCrosshair}
            onToggleThresholds={onToggleThresholds}
            onFullscreen={manageFullscreen || onFullscreenExternal ? handleToggleFullscreen : undefined}
            onExport={onExport}
            onRefresh={onRefresh}
            onAutoscale={onAutoscale}
            isFullscreen={isExpanded}
            isCrosshairActive={isCrosshairActive}
            thresholdsVisible={thresholdsVisible}
            isRefreshing={isRefreshing}
            channelLabel={channelLabel}
            channelSlot={channelSlot}
          />
        </div>
      )}

      <div
        ref={chartAreaRef}
        className={cn(
          "relative w-full min-w-0 rounded-lg border border-border/60 bg-[#FFFDF8]",
          isExpanded ? "min-h-0 flex-1" : "overflow-hidden"
        )}
        style={isExpanded ? { minHeight: chartHeight } : { height: chartHeight }}
      >
        {children({ height: chartHeight, isFullscreen: isExpanded })}
      </div>

      {statistics && <div className="mt-g2 shrink-0">{statistics}</div>}

      {hint && (
        <p className="mt-g2 shrink-0 text-[11px] text-muted-foreground leading-snug">{hint}</p>
      )}
    </div>
  );

  if (usePortalFallback) return createPortal(shell, document.body);
  return shell;
}

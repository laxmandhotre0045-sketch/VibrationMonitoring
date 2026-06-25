import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { computeFullscreenChartHeight } from "@/lib/chart-layout";
import { cn } from "@/lib/utils";
import { ChartHeader } from "../ChartHeader";
import { ChartToolbar } from "./ChartToolbar";

interface ChartContainerProps {
  title: string;
  channel: number;
  height?: number;
  hint?: string;
  autoscaleTitle?: string;
  onAutoscale?: () => void;
  onReset?: () => void;
  onExport?: () => void;
  onChartResize?: () => void;
  children: (props: { height: number; isFullscreen: boolean }) => React.ReactNode;
  className?: string;
}

function scheduleChartResize(callback?: () => void) {
  callback?.();
  requestAnimationFrame(() => callback?.());
  window.setTimeout(() => callback?.(), 100);
  window.setTimeout(() => callback?.(), 300);
}

/** Shared diagnostic chart card shell with fullscreen and toolbar actions. */
export function ChartContainer({
  title,
  channel,
  height = 280,
  hint = "Scroll to zoom frequency axis · Drag to pan · Y-axis stays fixed",
  autoscaleTitle,
  onAutoscale,
  onReset,
  onExport,
  onChartResize,
  children,
  className,
}: ChartContainerProps) {
  const shellRef = useRef<HTMLDivElement>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [usePortalFallback, setUsePortalFallback] = useState(false);
  const [measuredChartHeight, setMeasuredChartHeight] = useState(height);

  const measureChartArea = useCallback(() => {
    const area = chartAreaRef.current;
    if (!area) return;
    const next = Math.max(area.clientHeight, 360);
    if (next > 0) setMeasuredChartHeight(next);
  }, []);

  const handleToggleFullscreen = useCallback(async () => {
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
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      }
      await el.requestFullscreen();
    } catch {
      setUsePortalFallback(true);
      document.body.style.overflow = "hidden";
      scheduleChartResize(onChartResize);
    }
  }, [onChartResize, usePortalFallback]);

  useEffect(() => {
    const onFullscreenChange = () => {
      const el = shellRef.current;
      const nativeActive = !!el && document.fullscreenElement === el;
      setIsFullscreen(nativeActive || usePortalFallback);
      if (!nativeActive && !usePortalFallback) {
        document.body.style.overflow = "";
      }
      scheduleChartResize(onChartResize);
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [onChartResize, usePortalFallback]);

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
    if (!isFullscreen) {
      setMeasuredChartHeight(height);
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
  }, [isFullscreen, height, measureChartArea, onChartResize]);

  const isExpanded = isFullscreen || usePortalFallback;
  const chartHeight = isExpanded
    ? Math.max(measuredChartHeight, computeFullscreenChartHeight())
    : height;

  const shell = (
    <div
      ref={shellRef}
      className={cn(
        "diagnostic-chart-shell rounded-xl border border-border bg-white p-4",
        isExpanded && usePortalFallback &&
          "fixed inset-0 z-[200] m-0 flex h-dvh w-screen flex-col rounded-none border-0 p-4 sm:p-6",
        isExpanded && !usePortalFallback && "flex flex-col",
        className
      )}
      role={isExpanded ? "dialog" : undefined}
      aria-modal={isExpanded ? true : undefined}
      aria-label={isExpanded ? `${title} fullscreen view` : undefined}
    >
      <div className="mb-3 flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <ChartHeader title={title} channel={channel} className="mb-0 min-w-0 flex-1" />
        <ChartToolbar
          onAutoscale={onAutoscale}
          onReset={onReset}
          onExport={onExport}
          onToggleFullscreen={handleToggleFullscreen}
          isFullscreen={isExpanded}
          autoscaleTitle={autoscaleTitle}
        />
      </div>

      <div
        ref={chartAreaRef}
        className={cn(
          "relative w-full min-w-0",
          isExpanded ? "min-h-0 flex-1" : "overflow-hidden"
        )}
        style={isExpanded ? { minHeight: chartHeight } : { height: chartHeight }}
      >
        {children({ height: chartHeight, isFullscreen: isExpanded })}
      </div>

      <p className="mt-2 shrink-0 text-helper text-sm">{hint}</p>
    </div>
  );

  if (usePortalFallback) {
    return createPortal(shell, document.body);
  }

  return shell;
}

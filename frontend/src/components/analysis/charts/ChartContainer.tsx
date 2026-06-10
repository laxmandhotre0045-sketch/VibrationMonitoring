import React, { useCallback, useEffect, useState } from "react";
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
  const [isFullscreen, setIsFullscreen] = useState(false);

  const handleToggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  useEffect(() => {
    if (!isFullscreen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isFullscreen]);

  useEffect(() => {
    onChartResize?.();
  }, [isFullscreen, onChartResize]);

  const chartHeight = isFullscreen
    ? Math.max(window.innerHeight - 140, 360)
    : height;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-white p-4",
        isFullscreen && "fixed inset-0 z-50 m-0 flex flex-col rounded-none border-0 p-5",
        className
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <ChartHeader title={title} channel={channel} className="mb-0 min-w-0 flex-1" />
        <ChartToolbar
          onAutoscale={onAutoscale}
          onReset={onReset}
          onExport={onExport}
          onToggleFullscreen={handleToggleFullscreen}
          isFullscreen={isFullscreen}
          autoscaleTitle={autoscaleTitle}
        />
      </div>

      <div className={cn("w-full", isFullscreen && "min-h-0 flex-1")}>
        {children({ height: chartHeight, isFullscreen })}
      </div>

      <p className="mt-2 text-helper text-sm shrink-0">{hint}</p>
    </div>
  );
}

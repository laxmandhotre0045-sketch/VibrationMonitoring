import React from "react";
import {
  Crosshair,
  Download,
  Expand,
  Hand,
  Minimize2,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type GraphToolbarAction =
  | "zoomIn"
  | "zoomOut"
  | "pan"
  | "reset"
  | "crosshair"
  | "thresholds"
  | "fullscreen"
  | "export"
  | "refresh"
  | "autoscale";

interface GraphToolbarProps {
  actions?: GraphToolbarAction[];
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
  isFullscreen?: boolean;
  isPanActive?: boolean;
  isCrosshairActive?: boolean;
  thresholdsVisible?: boolean;
  isRefreshing?: boolean;
  channelLabel?: string;
  channelSlot?: React.ReactNode;
  className?: string;
}

function ToolbarButton({
  onClick,
  title,
  active,
  disabled,
  children,
}: {
  onClick?: () => void;
  title: string;
  active?: boolean;
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
        "inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors",
        "text-muted-foreground hover:bg-warm hover:text-foreground",
        "disabled:cursor-not-allowed disabled:opacity-40",
        active && "bg-signal-light/20 text-signal-dark ring-1 ring-signal-light/40"
      )}
    >
      {children}
    </button>
  );
}

const DEFAULT_ACTIONS: GraphToolbarAction[] = [
  "zoomIn",
  "zoomOut",
  "pan",
  "reset",
  "crosshair",
  "autoscale",
  "export",
  "fullscreen",
];

export function GraphToolbar({
  actions = DEFAULT_ACTIONS,
  onZoomIn,
  onZoomOut,
  onPan,
  onReset,
  onCrosshair,
  onToggleThresholds,
  onFullscreen,
  onExport,
  onRefresh,
  onAutoscale,
  isFullscreen = false,
  isPanActive = true,
  isCrosshairActive = true,
  thresholdsVisible = true,
  isRefreshing = false,
  channelLabel,
  channelSlot,
  className,
}: GraphToolbarProps) {
  const show = (action: GraphToolbarAction) => actions.includes(action);

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border border-border bg-[#FAFAF8] px-2 py-1.5",
        className
      )}
    >
      {channelSlot}
      {channelLabel && !channelSlot && (
        <span className="inline-flex h-8 items-center rounded-md border border-border bg-white px-2.5 text-xs font-semibold text-signal-dark">
          {channelLabel}
        </span>
      )}

      {(channelSlot || channelLabel) && (
        <div className="hidden sm:block h-5 w-px bg-border" />
      )}

      <div className="flex flex-wrap items-center gap-0.5">
        {show("zoomIn") && (
          <ToolbarButton onClick={onZoomIn} title="Zoom in">
            <ZoomIn className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("zoomIn") && show("zoomOut") && (
          <ToolbarButton onClick={onZoomOut} title="Zoom out">
            <ZoomOut className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("pan") && (
          <ToolbarButton onClick={onPan} title="Drag to pan (enabled)" active={isPanActive}>
            <Hand className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("reset") && (
          <ToolbarButton onClick={onReset} title="Reset zoom (double-click chart)">
            <RotateCcw className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("crosshair") && (
          <ToolbarButton
            onClick={onCrosshair}
            title="Toggle crosshair"
            active={isCrosshairActive}
          >
            <Crosshair className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("thresholds") && (
          <ToolbarButton
            onClick={onToggleThresholds}
            title={thresholdsVisible ? "Hide threshold lines" : "Show threshold lines"}
            active={thresholdsVisible}
          >
            <ShieldAlert className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("autoscale") && (
          <ToolbarButton onClick={onAutoscale} title="Fit all data">
            <Expand className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("refresh") && (
          <ToolbarButton onClick={onRefresh} title="Refresh" disabled={isRefreshing}>
            <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
          </ToolbarButton>
        )}
        {show("export") && (
          <ToolbarButton onClick={onExport} title="Export PNG">
            <Download className="h-4 w-4" />
          </ToolbarButton>
        )}
        {show("fullscreen") && (
          <ToolbarButton
            onClick={onFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Expand className="h-4 w-4" />
            )}
          </ToolbarButton>
        )}
      </div>
    </div>
  );
}

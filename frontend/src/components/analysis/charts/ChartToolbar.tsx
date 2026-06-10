import React from "react";
import { Download, Maximize2, Minimize2, RotateCcw, Expand } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChartToolbarProps {
  onAutoscale?: () => void;
  onReset?: () => void;
  onExport?: () => void;
  onToggleFullscreen?: () => void;
  isFullscreen?: boolean;
  autoscaleTitle?: string;
  className?: string;
}

function ActionButton({
  onClick,
  title,
  children,
}: {
  onClick?: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        "rounded-lg p-1.5 transition-colors",
        "text-muted-foreground hover:bg-warm hover:text-foreground",
        "disabled:opacity-40 disabled:cursor-not-allowed"
      )}
    >
      {children}
    </button>
  );
}

/** Reusable diagnostic chart action toolbar. */
export function ChartToolbar({
  onAutoscale,
  onReset,
  onExport,
  onToggleFullscreen,
  isFullscreen = false,
  autoscaleTitle = "Autoscale frequency axis — fit all data",
  className,
}: ChartToolbarProps) {
  return (
    <div className={cn("flex items-center gap-1 shrink-0", className)}>
      {onToggleFullscreen && (
        <ActionButton
          onClick={onToggleFullscreen}
          title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? (
            <Minimize2 className="h-3.5 w-3.5" />
          ) : (
            <Expand className="h-3.5 w-3.5" />
          )}
        </ActionButton>
      )}
      <ActionButton onClick={onAutoscale} title={autoscaleTitle}>
        <Maximize2 className="h-3.5 w-3.5" />
      </ActionButton>
      <ActionButton onClick={onReset} title="Reset axes">
        <RotateCcw className="h-3.5 w-3.5" />
      </ActionButton>
      <ActionButton onClick={onExport} title="Export image (PNG)">
        <Download className="h-3.5 w-3.5" />
      </ActionButton>
    </div>
  );
}

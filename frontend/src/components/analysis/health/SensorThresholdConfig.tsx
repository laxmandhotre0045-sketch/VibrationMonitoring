import React from "react";
import { SlidersHorizontal } from "lucide-react";
import { formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { cn } from "@/lib/utils";

interface SensorThresholdConfigProps {
  channelLabel: string;
  hasThresholds: boolean;
  cautionThreshold?: number;
  warningThreshold?: number;
  className?: string;
}

export function SensorThresholdConfig({
  channelLabel,
  hasThresholds,
  cautionThreshold,
  warningThreshold,
  className,
}: SensorThresholdConfigProps) {
  return (
    <div className={cn("rounded-md border border-border border-l-2 border-l-signal-light bg-white p-3 space-y-g2", className)}>
      <div className="flex items-center gap-2">
        <SlidersHorizontal size={22} className="text-signal-dark" aria-hidden />
        <h3 className="text-sm font-bold text-foreground">Sensor Threshold Configuration</h3>
        <span className="rounded-md border border-border bg-warm px-2 py-0.5 text-xs font-semibold text-signal-dark">
          {channelLabel}
        </span>
      </div>
      {hasThresholds ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
          <div className="rounded-md border border-border bg-surface/40 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Caution Limit
            </p>
            <p className="mt-g1 font-semibold text-foreground">
              {cautionThreshold !== undefined
                ? formatHealthMetricDisplay(cautionThreshold, "")
                : "—"}
            </p>
          </div>
          <div className="rounded-md border border-border bg-surface/40 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Warning Limit
            </p>
            <p className="mt-g1 font-semibold text-foreground">
              {warningThreshold !== undefined
                ? formatHealthMetricDisplay(warningThreshold, "")
                : "—"}
            </p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          No threshold configuration saved for this sensor/channel set.
        </p>
      )}
    </div>
  );
}

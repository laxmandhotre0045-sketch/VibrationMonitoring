import React from "react";
import type { FeatureMonitorStatus } from "@/types/features";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<
  FeatureMonitorStatus,
  { label: string; className: string }
> = {
  normal: {
    label: "Normal",
    className: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/30",
  },
  warning: {
    label: "Warning",
    className: "bg-signal-light/15 text-signal-dark border-signal-light/40",
  },
  critical: {
    label: "Critical",
    className: "bg-destructive/10 text-destructive border-destructive/30",
  },
  no_baseline: {
    label: "No Baseline",
    className: "bg-muted/50 text-muted-foreground border-border",
  },
};

interface FeatureStatusBadgeProps {
  status: FeatureMonitorStatus;
  className?: string;
}

export function FeatureStatusBadge({ status, className }: FeatureStatusBadgeProps) {
  const config = STATUS_STYLES[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}

export function featureStatusLabel(status: FeatureMonitorStatus): string {
  return STATUS_STYLES[status].label;
}

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
  not_assessed: {
    label: "Not Assessed",
    className: "bg-muted/30 text-muted-foreground border-dashed border-border",
  },
};

interface FeatureStatusBadgeProps {
  status: FeatureMonitorStatus;
  className?: string;
}

export function FeatureStatusBadge({ status, className }: FeatureStatusBadgeProps) {
  // Falls back rather than reading undefined off the map. A status added to
  // the backend before this file catches up should render a grey chip, not
  // take the analysis page down with it.
  const config = STATUS_STYLES[status] ?? STATUS_STYLES.not_assessed;
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
  return (STATUS_STYLES[status] ?? STATUS_STYLES.not_assessed).label;
}

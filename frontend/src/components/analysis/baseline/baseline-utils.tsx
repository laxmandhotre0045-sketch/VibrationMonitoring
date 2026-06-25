import React from "react";
import type { Baseline } from "@/types/baseline";
import { cn } from "@/lib/utils";

export type BaselinePlotStatus = "ready" | "partial" | "pending" | "failed" | "unknown";

const STATUS_STYLES: Record<
  BaselinePlotStatus,
  { label: string; className: string }
> = {
  ready: {
    label: "Ready",
    className: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/30",
  },
  partial: {
    label: "Partial",
    className: "bg-signal-light/15 text-signal-dark border-signal-light/40",
  },
  pending: {
    label: "Pending",
    className: "bg-muted/50 text-muted-foreground border-border",
  },
  failed: {
    label: "Failed",
    className: "bg-destructive/10 text-destructive border-destructive/30",
  },
  unknown: {
    label: "Unknown",
    className: "bg-muted/50 text-muted-foreground border-border",
  },
};

export function normalizeBaselinePlotStatus(status: string | undefined): BaselinePlotStatus {
  const raw = String(status ?? "").toLowerCase();
  if (raw === "ready") return "ready";
  if (raw === "partial") return "partial";
  if (raw === "pending") return "pending";
  if (raw === "failed") return "failed";
  return "unknown";
}

interface BaselinePlotStatusBadgeProps {
  status: string | undefined;
  className?: string;
}

export function BaselinePlotStatusBadge({ status, className }: BaselinePlotStatusBadgeProps) {
  const normalized = normalizeBaselinePlotStatus(status);
  const config = STATUS_STYLES[normalized];
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

export function baselineMatchesFilter(
  baseline: Baseline,
  filter: BaselineListFilter
): boolean {
  const plotStatus = normalizeBaselinePlotStatus(baseline.plots_status);
  switch (filter) {
    case "all":
      return true;
    case "primary":
      return baseline.is_primary;
    case "ready":
      return plotStatus === "ready";
    case "pending":
      return plotStatus === "pending" || plotStatus === "partial";
    case "failed":
      return plotStatus === "failed";
    default:
      return true;
  }
}

export type BaselineListFilter = "all" | "primary" | "ready" | "pending" | "failed";

export function filterBaselines(
  baselines: Baseline[],
  options: { search: string; filter: BaselineListFilter; formatDateTime: (iso: string) => string }
): Baseline[] {
  const query = options.search.trim().toLowerCase();
  return baselines.filter((baseline) => {
    if (!baselineMatchesFilter(baseline, options.filter)) return false;
    if (!query) return true;
    const nameMatch = baseline.name.toLowerCase().includes(query);
    const dateMatch = options.formatDateTime(baseline.created_at).toLowerCase().includes(query);
    return nameMatch || dateMatch;
  });
}

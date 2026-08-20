import React from "react";
import type { FeatureSummaryCounts } from "@/types/features";
import { cn } from "@/lib/utils";

interface HealthSummaryCardsProps {
  summary: FeatureSummaryCounts;
  className?: string;
}

const CARD_CONFIG = [
  {
    key: "total" as const,
    label: "Total Features",
    valueClass: "text-brand",
    boxClass: "border-border bg-white",
  },
  {
    key: "normal" as const,
    label: "Normal",
    valueClass: "text-machine-healthy",
    boxClass: "border-machine-healthy/25 bg-machine-healthy/5",
  },
  {
    key: "warning" as const,
    label: "Warning",
    valueClass: "text-signal-dark",
    boxClass: "border-signal-light/35 bg-signal-light/10",
  },
  {
    key: "critical" as const,
    label: "Critical",
    valueClass: "text-destructive",
    boxClass: "border-destructive/25 bg-destructive/5",
  },
  {
    key: "no_baseline" as const,
    label: "No Baseline",
    valueClass: "text-muted-foreground",
    boxClass: "border-border bg-muted/20",
  },
];

export function HealthSummaryCards({ summary, className }: HealthSummaryCardsProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3",
        className
      )}
    >
      {CARD_CONFIG.map((card) => (
        <div
          key={card.key}
          className={cn(
            "rounded-xl border border-l-2 border-l-signal-light px-g4 py-g3 min-h-[88px]",
            "shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md",
            card.boxClass
          )}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {card.label}
          </p>
          <p className={cn("mt-g2 text-2xl font-bold leading-none", card.valueClass)}>
            {summary[card.key]}
          </p>
        </div>
      ))}
    </div>
  );
}

export function HealthSummaryCardsSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3", className)}>
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-white px-g4 py-g3 min-h-[88px] animate-pulse"
        >
          <div className="h-3 w-20 rounded bg-muted/60" />
          <div className="mt-g3 h-7 w-12 rounded bg-muted/80" />
        </div>
      ))}
    </div>
  );
}

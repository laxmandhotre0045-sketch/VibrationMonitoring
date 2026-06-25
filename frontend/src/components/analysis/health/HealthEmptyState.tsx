import React from "react";
import { BarChart2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface HealthEmptyStateProps {
  message?: string;
  className?: string;
}

export function HealthEmptyState({
  message = "No feature data available for this channel.",
  className,
}: HealthEmptyStateProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-border bg-surface/40 px-6 py-10 text-center",
        className
      )}
    >
      <BarChart2 size={28} className="mx-auto mb-2 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium text-muted-foreground">{message}</p>
    </div>
  );
}

import React from "react";
import { cn } from "@/lib/utils";

interface ChartHeaderProps {
  title: string;
  channel: number;
  className?: string;
}

/** Reusable diagnostic plot header — title and channel badge. */
export function ChartHeader({ title, channel, className }: ChartHeaderProps) {
  return (
    <div className={cn("mb-3 flex items-center justify-between gap-2", className)}>
      <h3 className="text-card-title min-w-0 truncate">{title}</h3>
      <span className="shrink-0 rounded-md border border-border bg-warm px-2 py-0.5 text-sm font-semibold text-signal-dark">
        ch{channel}
      </span>
    </div>
  );
}

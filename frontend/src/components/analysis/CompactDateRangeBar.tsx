import React from "react";
import { CalendarRange } from "lucide-react";
import { cn } from "@/lib/utils";

const compactInput = cn(
  "h-7 rounded-md border border-border bg-white px-2 text-sm text-foreground",
  "focus:outline-none focus:border-signal-light focus:ring-1 focus:ring-[rgba(245,166,35,0.22)]",
  "disabled:cursor-not-allowed disabled:opacity-50"
);

interface CompactDateRangeBarProps {
  fromDate: string;
  toDate: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}

export function CompactDateRangeBar({
  fromDate,
  toDate,
  onFromChange,
  onToChange,
  disabled = false,
  className,
}: CompactDateRangeBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface/50 px-2.5 py-1.5",
        className
      )}
    >
      <span className="inline-flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <CalendarRange size={14} className="text-signal-dark" aria-hidden />
        Range
      </span>
      <label className="inline-flex items-center gap-1.5 text-sm text-foreground">
        <span className="text-sm font-medium text-muted-foreground">From</span>
        <input
          type="date"
          className={compactInput}
          value={fromDate}
          max={toDate || undefined}
          disabled={disabled}
          onChange={(e) => onFromChange(e.target.value)}
          aria-label="From date"
        />
      </label>
      <span className="hidden sm:inline text-muted-foreground/50" aria-hidden>
        —
      </span>
      <label className="inline-flex items-center gap-1.5 text-sm text-foreground">
        <span className="text-sm font-medium text-muted-foreground">To</span>
        <input
          type="date"
          className={compactInput}
          value={toDate}
          min={fromDate || undefined}
          disabled={disabled}
          onChange={(e) => onToChange(e.target.value)}
          aria-label="To date"
        />
      </label>
    </div>
  );
}

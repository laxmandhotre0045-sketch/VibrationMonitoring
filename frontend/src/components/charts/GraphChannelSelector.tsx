import React from "react";
import { channelLabel } from "@/lib/health-metrics";
import { cn } from "@/lib/utils";

interface GraphChannelSelectorProps {
  value: number;
  channelCount: number;
  onChange: (channel: number) => void;
  disabled?: boolean;
  className?: string;
}

export function GraphChannelSelector({
  value,
  channelCount,
  onChange,
  disabled = false,
  className,
}: GraphChannelSelectorProps) {
  const count = Math.max(1, channelCount);

  return (
    <div
      className={cn(
        "inline-flex flex-wrap items-center gap-1 rounded-lg border border-border bg-warm p-0.5",
        className
      )}
      role="tablist"
      aria-label="Channel selection"
    >
      {Array.from({ length: count }, (_, i) => {
        const active = value === i;
        return (
          <button
            key={i}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(i)}
            className={cn(
              "h-8 min-w-[52px] rounded-md px-2.5 text-xs font-semibold transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45",
              active
                ? "bg-white text-signal-dark shadow-sm ring-1 ring-signal-light/30"
                : "text-muted-foreground hover:bg-white/80 hover:text-foreground",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            {channelLabel(i)}
          </button>
        );
      })}
    </div>
  );
}

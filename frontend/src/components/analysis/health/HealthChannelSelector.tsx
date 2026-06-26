import React from "react";
import { ChevronDown } from "lucide-react";
import { HEALTH_CHANNEL_COUNT } from "@/types/health-status";
import { channelLabel } from "@/lib/health-metrics";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { cn } from "@/lib/utils";

interface HealthChannelSelectorProps {
  value: number;
  onChange: (channel: number) => void;
  channelCount?: number;
  disabled?: boolean;
  className?: string;
}

export function HealthChannelSelector({
  value,
  onChange,
  channelCount = HEALTH_CHANNEL_COUNT,
  disabled = false,
  className,
}: HealthChannelSelectorProps) {
  const count = Math.max(1, channelCount);
  return (
    <div className={cn("flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3", className)}>
      <label className="text-sm font-semibold text-muted-foreground uppercase tracking-wide shrink-0">
        Channel
      </label>
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <div className="relative min-w-[140px]">
          <select
            className={cn(analysisSelectClass, "pr-8")}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-label="Health status channel"
          >
            {Array.from({ length: count }, (_, i) => (
              <option key={i} value={i}>
                {channelLabel(i)}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
        </div>
        <span className="inline-flex items-center rounded-md border border-border bg-warm px-2.5 py-1 text-sm font-semibold text-signal-dark">
          {channelLabel(value)}
        </span>
      </div>
    </div>
  );
}

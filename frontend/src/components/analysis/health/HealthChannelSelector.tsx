import React from "react";
import { HEALTH_CHANNEL_COUNT } from "@/types/health-status";
import { channelLabel } from "@/lib/health-metrics";
import { GraphChannelSelector } from "@/components/charts";
import { cn } from "@/lib/utils";

interface HealthChannelSelectorProps {
  value: number;
  onChange: (channel: number) => void;
  channelCount?: number;
  disabled?: boolean;
  className?: string;
}

/**
 * Channel picker for the health / feature-trend views.
 *
 * A dropdown hid every other channel behind a click, which is the wrong shape
 * for a monitoring console where switching channels is the main interaction.
 * The segmented control from the charts kit (already used by Detailed Analysis)
 * puts CH-1…CH-n on one row with the active one highlighted; the badge on the
 * right restates the current selection for the cards below it.
 *
 * Selection state still lives with the caller — same `value` / `onChange`.
 */
export function HealthChannelSelector({
  value,
  onChange,
  channelCount = HEALTH_CHANNEL_COUNT,
  disabled = false,
  className,
}: HealthChannelSelectorProps) {
  const count = Math.max(1, channelCount);

  return (
    <div
      className={cn(
        "flex flex-col gap-g2 rounded-xl border border-border bg-white px-g4 py-g3 shadow-[0_1px_3px_rgba(21,54,109,0.05)]",
        "sm:flex-row sm:items-center sm:justify-between sm:gap-g3",
        className
      )}
    >
      <div className="flex flex-col gap-g2 min-w-0 sm:flex-row sm:items-center sm:gap-g3">
        <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Channel
        </span>
        <GraphChannelSelector
          value={value}
          channelCount={count}
          onChange={onChange}
          disabled={disabled}
        />
      </div>

      <span
        className={cn(
          "inline-flex shrink-0 items-center gap-1.5 self-start rounded-md border border-signal-light/40",
          "bg-signal-light/10 px-2.5 py-1 text-xs font-bold tracking-wide text-signal-dark sm:self-auto"
        )}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-signal-light" aria-hidden />
        {channelLabel(value)}
      </span>
    </div>
  );
}

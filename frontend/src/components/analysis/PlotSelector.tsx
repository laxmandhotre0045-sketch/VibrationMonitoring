import React from "react";
import { PLOT_LABELS, PLOT_TYPES, type PlotType } from "@/types/measurements";
import { cn } from "@/lib/utils";

export interface PlotSelectorOption {
  type: PlotType;
  label: string;
  disabled?: boolean;
}

interface PlotSelectorProps {
  value: PlotType;
  onChange: (plotType: PlotType) => void;
  /** Plot types returned by the API; others render disabled. */
  availableTypes?: PlotType[];
  className?: string;
  compact?: boolean;
}

function buildOptions(availableTypes?: PlotType[]): PlotSelectorOption[] {
  const available = availableTypes ? new Set(availableTypes) : null;

  return PLOT_TYPES.map((type) => ({
    type,
    label: PLOT_LABELS[type],
    disabled: available ? !available.has(type) : false,
  }));
}

/** Reusable diagnostic plot tab selector — extend PLOT_TYPES to add future plots. */
export function PlotSelector({
  value,
  onChange,
  availableTypes,
  className,
  compact = false,
}: PlotSelectorProps) {
  const options = buildOptions(availableTypes);

  return (
    <div
      className={cn("overflow-x-auto scrollbar-thin -mx-1 px-1", className)}
      role="tablist"
      aria-label="Diagnostic plot type"
    >
      <div className={cn("inline-flex w-full flex-wrap gap-1 rounded-lg border border-border bg-[#F5F3EF] p-1", compact && "gap-0.5")}>
        {options.map((option) => {
          const isActive = value === option.type;

          return (
            <button
              key={option.type}
              type="button"
              role="tab"
              aria-selected={isActive}
              disabled={option.disabled}
              onClick={() => onChange(option.type)}
              className={cn(
                "h-9 min-w-[108px] flex-1 rounded-md font-semibold whitespace-nowrap transition-all duration-200",
                compact ? "px-2.5 text-xs" : "px-3 text-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45",
                isActive
                  ? "bg-white text-signal-dark shadow-sm ring-1 ring-signal-light/35"
                  : "text-muted-foreground hover:bg-white/70 hover:text-foreground",
                option.disabled && "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-muted-foreground"
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

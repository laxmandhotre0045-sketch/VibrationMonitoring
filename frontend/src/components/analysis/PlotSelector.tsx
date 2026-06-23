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
      <div className={cn("inline-flex min-w-full gap-0.5 rounded-md border border-border bg-warm p-0.5 sm:flex-wrap sm:min-w-0", compact && "p-0.5")}>
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
                "shrink-0 rounded-md font-semibold whitespace-nowrap transition-colors",
                compact ? "px-2.5 py-1.5 text-sm" : "px-3 py-2 text-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(245,166,35,0.22)]",
                isActive
                  ? "bg-cta text-cta-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-white hover:text-foreground",
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

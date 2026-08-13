import React from "react";
import { THRESHOLD_LEVEL_META, THRESHOLD_LEVEL_ORDER } from "@/lib/threshold-overlay";
import { cn } from "@/lib/utils";

interface ThresholdZoneLegendProps {
  visible?: boolean;
  className?: string;
}

/** Industrial alarm zone legend — green / amber / red (Randall, CM with Vibration Signals). */
export function ThresholdZoneLegend({ visible = true, className }: ThresholdZoneLegendProps) {
  if (!visible) return null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground",
        className
      )}
      aria-label="Threshold zone legend"
    >
      {THRESHOLD_LEVEL_ORDER.map((level) => {
        const meta = THRESHOLD_LEVEL_META[level];
        return (
          <span key={level} className="inline-flex items-center gap-1.5">
            <span
              className="h-0.5 w-4 rounded-full"
              style={{
                backgroundColor: meta.color,
                borderTop: meta.lineType === "dashed" ? `1px dashed ${meta.color}` : undefined,
              }}
            />
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}

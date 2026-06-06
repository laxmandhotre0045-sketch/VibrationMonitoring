import React from "react";
import { BarChart3 } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
import { COMPLETENESS_SECTIONS } from "@/lib/industrial-metadata";
import { getStepCompletion } from "@/lib/form-intelligence";
import { cn } from "@/lib/utils";

interface CompletenessEngineProps {
  data: EquipmentFormData;
}

export function CompletenessEngine({ data }: CompletenessEngineProps) {
  return (
    <div className="bg-card border border-border rounded-xl">
      <div className="px-8 py-5 border-b border-border flex items-center gap-3">
        <BarChart3 size={20} className="text-signal-dark" />
        <h3 className="text-xl font-semibold text-brand">Configuration Completeness</h3>
      </div>
      <div className="p-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
        {COMPLETENESS_SECTIONS.map((section) => {
          const pct = getStepCompletion(data, section.id);
          return (
            <div key={section.key} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-base font-medium text-brand truncate">{section.label}</span>
                <span
                  className={cn(
                    "text-base font-semibold shrink-0 tabular-nums",
                    pct >= 80 ? "text-signal-dark" : pct >= 50 ? "text-signal-light" : "text-muted-foreground"
                  )}
                >
                  {pct}%
                </span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    pct >= 50 ? "signal-gradient" : "bg-signal-light/40"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                {pct >= 100 ? "Complete" : pct > 0 ? "In Progress" : "Not Started"}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

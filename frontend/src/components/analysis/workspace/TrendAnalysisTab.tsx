import React from "react";
import { LineChart } from "lucide-react";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";

interface TrendAnalysisTabProps {
  selectedUploadId: string;
}

export function TrendAnalysisTab({ selectedUploadId }: TrendAnalysisTabProps) {
  return (
    <div className={analysisBodyStack}>
      <div className="rounded-xl border border-dashed border-border bg-muted/10 px-g4 py-g6 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-brand/5 text-brand">
          <LineChart size={24} aria-hidden />
        </div>
        <h3 className="mt-4 text-base font-bold text-foreground">Factor trends moved to Status (Health)</h3>
        <p className="mt-2 text-sm text-muted-foreground max-w-lg mx-auto">
          Per-capture feature values, status tables, baseline comparison, and segment trend charts
          are now on the Status (Health) tab for the selected timeline capture.
        </p>
        {!selectedUploadId && (
          <p className="mt-4 text-sm text-muted-foreground">
            Select a capture on the timeline to open Status (Health).
          </p>
        )}
      </div>
    </div>
  );
}

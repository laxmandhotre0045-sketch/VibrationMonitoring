import React from "react";
import { LineChart } from "lucide-react";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";

interface TrendAnalysisTabProps {
  selectedUploadId: string;
}

/**
 * Placeholder, and deliberately specific about what is and is not available.
 *
 * Two different things get called "trend" here, and an earlier version of this
 * card blurred them: Status (Health) trends a feature across the 32 segments
 * *within one capture* (`GET /uploads/{id}/factor-trends`, keyed to a single
 * upload_id). Trending a feature *across captures* over weeks is a separate
 * view that does not exist in the UI yet. Saying the content simply "moved"
 * sent anyone looking for the second one to a tab that does not have it.
 */
export function TrendAnalysisTab({ selectedUploadId }: TrendAnalysisTabProps) {
  return (
    <div className={analysisBodyStack}>
      <div className="rounded-xl border border-dashed border-border bg-muted/10 px-g4 py-g6 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-brand/5 text-brand">
          <LineChart size={24} aria-hidden />
        </div>
        <h3 className="mt-g3 text-base font-bold text-foreground">
          Trending across captures is not available yet
        </h3>
        <p className="mt-g2 text-sm text-muted-foreground max-w-xl mx-auto">
          For the capture selected on the timeline, Status (Health) has the feature values,
          status tables, baseline comparison and the segment trend charts that run across
          that one capture.
        </p>
        <p className="mt-g2 text-sm text-muted-foreground max-w-xl mx-auto">
          Following a single feature across many captures over days or weeks is a separate
          view, and it has not been built yet.
        </p>
        {!selectedUploadId && (
          <p className="mt-g3 text-sm text-muted-foreground">
            Select a capture on the timeline to open Status (Health).
          </p>
        )}
      </div>
    </div>
  );
}

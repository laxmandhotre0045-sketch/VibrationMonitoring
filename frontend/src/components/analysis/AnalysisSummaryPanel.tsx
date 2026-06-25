import React from "react";
import { BarChart2, Bookmark } from "lucide-react";
import type { SensorDataUpload } from "@/types/measurements";
import { formatCaptureSelection } from "@/lib/upload-format";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  analysisChannelBtnClass,
  analysisGridGap,
  analysisKpiClass,
  analysisKpiLabelClass,
  analysisKpiValueClass,
} from "./analysis-layout";

interface AnalysisSummaryPanelProps {
  selectedUpload: SensorDataUpload | null | undefined;
  plotChannelCount: number;
  activeChannel: number;
  onChannelChange: (channel: number) => void;
  canWrite: boolean;
  onSaveBaseline?: () => void;
  saveBaselineDisabled?: boolean;
  showCaptureSummary?: boolean;
  className?: string;
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className={cn(analysisKpiClass, "border-l-2 border-l-signal-light")}>
      <p className={analysisKpiLabelClass}>{label}</p>
      <p className={cn(analysisKpiValueClass, "truncate")} title={value}>
        {value}
      </p>
    </div>
  );
}

export function AnalysisSummaryPanel({
  selectedUpload,
  plotChannelCount,
  activeChannel,
  onChannelChange,
  canWrite,
  onSaveBaseline,
  saveBaselineDisabled,
  showCaptureSummary = true,
  className,
}: AnalysisSummaryPanelProps) {
  if (!selectedUpload) {
    return (
      <div
        className={cn(
          "rounded-md border border-dashed border-border bg-surface/40 px-4 py-5 text-center",
          className
        )}
      >
        <BarChart2 size={28} className="mx-auto mb-1.5 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">
          Select a capture on the timeline to view analysis details.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {showCaptureSummary && (
        <>
          <div className="rounded-md border border-border border-l-2 border-l-signal-light bg-white px-3 py-2">
            <p className={analysisKpiLabelClass}>Selected Capture</p>
            <p className="text-sm font-medium text-foreground mt-1 leading-snug" title={formatCaptureSelection(selectedUpload)}>
              {formatCaptureSelection(selectedUpload)}
            </p>
          </div>

          <div className={cn("grid grid-cols-2 sm:grid-cols-4", analysisGridGap)}>
            <MetricCard
              label="Samples"
              value={selectedUpload.sample_count?.toLocaleString() ?? "—"}
            />
            <MetricCard label="Channels" value={String(selectedUpload.channel_count)} />
            <MetricCard label="Parse Status" value={selectedUpload.parse_status} />
            <MetricCard label="Plots Status" value={selectedUpload.plots_status} />
          </div>
        </>
      )}

      <div>
        <p className={cn(analysisKpiLabelClass, "mb-1.5")}>View Channel</p>
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: plotChannelCount }, (_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onChannelChange(i)}
              className={cn(
                analysisChannelBtnClass,
                activeChannel === i
                  ? "bg-cta text-cta-foreground"
                  : "border border-border bg-white text-muted-foreground hover:bg-surface"
              )}
            >
              ch{i}
            </button>
          ))}
        </div>
      </div>

      {selectedUpload.parse_status === "parsed" && canWrite && onSaveBaseline && (
        <Button
          variant="secondary"
          size="sm"
          icon={<Bookmark size={14} />}
          onClick={onSaveBaseline}
          disabled={saveBaselineDisabled}
        >
          Save as baseline
        </Button>
      )}
    </div>
  );
}

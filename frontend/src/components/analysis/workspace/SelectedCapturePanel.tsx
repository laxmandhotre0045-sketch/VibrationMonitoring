import React from "react";
import { FileAudio2 } from "lucide-react";
import type { SensorDataUpload } from "@/types/measurements";
import { formatCaptureSelection } from "@/lib/upload-format";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisCardPad,
  analysisGridGap,
  analysisKpiClass,
  analysisKpiLabelClass,
  analysisKpiValueClass,
} from "@/components/analysis/analysis-layout";
import { cn } from "@/lib/utils";

interface SelectedCapturePanelProps {
  selectedUpload: SensorDataUpload | null | undefined;
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

export function SelectedCapturePanel({ selectedUpload }: SelectedCapturePanelProps) {
  return (
    <GlassCard className={analysisCardPad} delay={0.13}>
      <AnalysisSectionHeader
        icon={FileAudio2}
        title="Selected Capture"
        subtitle="Active capture used across all analysis tabs."
      />
      {!selectedUpload ? (
        <p className="text-sm text-muted-foreground">
          Select a capture on the timeline to view capture details.
        </p>
      ) : (
        <div className="space-y-3">
          <div className="rounded-md border border-border border-l-2 border-l-signal-light bg-white px-3 py-2">
            <p className={analysisKpiLabelClass}>Capture</p>
            <p
              className="text-sm font-medium text-foreground mt-1 leading-snug"
              title={formatCaptureSelection(selectedUpload)}
            >
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
        </div>
      )}
    </GlassCard>
  );
}

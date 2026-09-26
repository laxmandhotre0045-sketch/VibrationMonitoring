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
import { CaptureTrustBadge } from "@/components/analysis/workspace/CaptureTrustBadge";
import { useCaptureTrust } from "@/hooks/useCaptureTrust";
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
  const trust = useCaptureTrust(selectedUpload?.id);

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
        <div className="space-y-g3">
          <div className="rounded-md border border-border border-l-2 border-l-signal-light bg-white px-3 py-2">
            <div className="flex flex-wrap items-start justify-between gap-g2">
              <div className="min-w-0">
                <p className={analysisKpiLabelClass}>Capture</p>
                <p
                  className="text-sm font-medium text-foreground mt-g1 leading-snug"
                  title={formatCaptureSelection(selectedUpload)}
                >
                  {formatCaptureSelection(selectedUpload)}
                </p>
              </div>

              {/* Beside the capture, not below the plots. The point is that an
                  analyst sees the data is untrustworthy before reading anything
                  from it, rather than after reaching a conclusion. */}
              <CaptureTrustBadge
                trustLevel={trust.trustLevel}
                failedChecks={trust.failedChecks}
                notAssessedChecks={trust.notAssessedChecks}
                isLoading={trust.isLoading}
                className="max-w-[18rem] shrink-0"
              />
            </div>
          </div>
          <div className={cn("grid grid-cols-2 sm:grid-cols-4", analysisGridGap)}>
            <MetricCard
              label="Samples"
              value={selectedUpload.sample_count?.toLocaleString() ?? "—"}
            />
            <MetricCard label="Channels" value={String(selectedUpload.channel_count)} />
            <MetricCard label="Parsing" value={selectedUpload.parse_status} />
            <MetricCard label="Plots" value={selectedUpload.plots_status} />
            <MetricCard
              label="Features"
              value={selectedUpload.features_status ?? "pending"}
            />
          </div>
        </div>
      )}
    </GlassCard>
  );
}

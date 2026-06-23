import React from "react";
import { Activity } from "lucide-react";
import type { SensorDataUpload } from "@/types/measurements";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "./AnalysisSectionHeader";
import { CaptureTimelinePanel } from "./CaptureTimelinePanel";
import { analysisCardPad } from "./analysis-layout";

interface CaptureTimelineSectionProps {
  sensorId: string;
  selectedUploadId: string;
  onSelectUpload: (uploadId: string, upload?: SensorDataUpload) => void;
  refreshKey?: number;
}

export function CaptureTimelineSection({
  sensorId,
  selectedUploadId,
  onSelectUpload,
  refreshKey = 0,
}: CaptureTimelineSectionProps) {
  return (
    <GlassCard className={analysisCardPad} delay={0.12}>
      <AnalysisSectionHeader
        icon={Activity}
        title="3. Capture Timeline"
        subtitle="Browse uploads by date range and select a capture for analysis."
      />
      <CaptureTimelinePanel
        sensorId={sensorId}
        selectedUploadId={selectedUploadId}
        onSelectUpload={onSelectUpload}
        refreshKey={refreshKey}
      />
    </GlassCard>
  );
}

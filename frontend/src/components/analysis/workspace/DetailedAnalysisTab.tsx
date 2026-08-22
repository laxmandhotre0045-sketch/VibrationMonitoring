import React from "react";
import { BarChart3 } from "lucide-react";
import type { PlotSeries, PlotType, SensorDataUpload } from "@/types/measurements";
import { DiagnosticChart } from "@/components/analysis/DiagnosticChart";
import { PlotSelector } from "@/components/analysis/PlotSelector";
import { AnalysisSummaryPanel } from "@/components/analysis/AnalysisSummaryPanel";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { GraphChannelSelector } from "@/components/charts";
import { GRAPH_PRIMARY_HEIGHT } from "@/lib/chart-constants";
import {
  analysisBodyStack,
  analysisGridGap,
  analysisInputClass,
} from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

interface DetailedAnalysisTabProps {
  selectedUpload: SensorDataUpload | null | undefined;
  plotChannelCount: number;
  activeChannel: number;
  onChannelChange: (channel: number) => void;
  channelCount: number;
  onChannelCountChange: (count: number) => void;
  samplingRate: number;
  onSamplingRateChange: (rate: number) => void;
  fftLines: number;
  onFftLinesChange: (lines: number) => void;
  canWrite: boolean;
  sensorId: string;
  onSaveConfig: () => void;
  saveConfigPending: boolean;
  plotConfigExists: boolean;
  onSaveBaseline?: () => void;
  saveBaselineDisabled?: boolean;
  plotsEnabled: boolean;
  plotsLoading: boolean;
  plotsError: unknown;
  plotsData: { plots: PlotSeries[] } | undefined;
  availablePlotTypes: PlotType[];
  activePlotType: PlotType;
  onPlotTypeChange: (type: PlotType) => void;
  activePlot: PlotSeries | undefined;
  plotSource: "upload" | "baseline";
  selectedUploadId: string;
  selectedBaselineId: string;
}

export function DetailedAnalysisTab({
  selectedUpload,
  plotChannelCount,
  activeChannel,
  onChannelChange,
  channelCount,
  onChannelCountChange,
  samplingRate,
  onSamplingRateChange,
  fftLines,
  onFftLinesChange,
  canWrite,
  sensorId,
  onSaveConfig,
  saveConfigPending,
  plotConfigExists,
  onSaveBaseline,
  saveBaselineDisabled,
  plotsEnabled,
  plotsLoading,
  plotsError,
  plotsData,
  availablePlotTypes,
  activePlotType,
  onPlotTypeChange,
  activePlot,
  plotSource,
  selectedUploadId,
  selectedBaselineId,
}: DetailedAnalysisTabProps) {
  return (
    <div className={analysisBodyStack}>
      <div className={cn("grid grid-cols-2 lg:grid-cols-4", analysisGridGap)}>
        <FormField label="Sampling Rate (Hz)" compact>
          <TextInput
            type="number"
            className={analysisInputClass}
            value={samplingRate}
            onChange={(e) => onSamplingRateChange(Number(e.target.value))}
          />
        </FormField>
        <FormField label="FFT Lines" compact>
          <TextInput
            type="number"
            className={analysisInputClass}
            value={fftLines}
            onChange={(e) => onFftLinesChange(Number(e.target.value))}
          />
        </FormField>
        <FormField label="Channel Count" compact>
          <TextInput
            type="number"
            min={1}
            max={32}
            className={analysisInputClass}
            value={channelCount}
            onChange={(e) => onChannelCountChange(Number(e.target.value))}
          />
        </FormField>
        <div className="flex items-end">
          <Button
            size="sm"
            className="w-full"
            onClick={onSaveConfig}
            disabled={!sensorId || saveConfigPending || !canWrite}
          >
            Save Plot Configuration
          </Button>
        </div>
      </div>

      {!canWrite && (
        <p className="text-sm text-muted-foreground">
          Read-only users cannot save plot configuration.
        </p>
      )}
      {plotConfigExists && (
        <p className="text-sm text-machine-healthy font-medium">
          Configuration exists for this sensor.
        </p>
      )}

      <AnalysisSectionHeader icon={BarChart3} title="Analysis Controls" className="mb-0 pb-0 border-b-0" />

      <div className={cn("grid lg:grid-cols-2", analysisGridGap)}>
        <AnalysisSummaryPanel
          selectedUpload={selectedUpload}
          plotChannelCount={plotChannelCount}
          activeChannel={activeChannel}
          onChannelChange={onChannelChange}
          canWrite={canWrite}
          onSaveBaseline={onSaveBaseline}
          saveBaselineDisabled={saveBaselineDisabled}
          showCaptureSummary={false}
        />
        <div className="space-y-g3">
          {plotsLoading && <p className="text-sm text-muted-foreground">Loading analysis data…</p>}
          {!!plotsError && (
            <p className="text-sm text-destructive font-semibold">
              Failed to load plots:{" "}
              {(plotsError as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
                "Try another channel or select a different capture."}
            </p>
          )}
          {!plotsEnabled && !plotsLoading && (
            <p className="text-sm text-muted-foreground">
              Select a capture on the timeline to load analysis plots.
            </p>
          )}
          {plotsEnabled && plotsData && plotsData.plots.length === 0 && !plotsLoading && (
            <p className="text-sm font-semibold text-signal-dark">
              No plots returned. Try channel ch0 or check plot configuration.
            </p>
          )}
        </div>
      </div>

      {activePlot && (
        <div className="w-full space-y-g2">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-g1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Channel
              </p>
              <GraphChannelSelector
                value={activeChannel}
                channelCount={plotChannelCount}
                onChange={onChannelChange}
                disabled={!plotsEnabled}
              />
            </div>
            {plotsEnabled && plotsData && plotsData.plots.length > 0 && (
              <div className="flex-1 min-w-0 space-y-g1">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Plot Type
                </p>
                <PlotSelector
                  value={activePlotType}
                  onChange={onPlotTypeChange}
                  availableTypes={availablePlotTypes}
                />
              </div>
            )}
          </div>

          <DiagnosticChart
            key={`${activePlot.plot_type}-${activePlot.channel}-${plotSource}-${selectedUploadId}-${selectedBaselineId}`}
            plot={activePlot}
            height={GRAPH_PRIMARY_HEIGHT}
            samplingRateHz={samplingRate}
          />
        </div>
      )}

      {!plotsEnabled && !plotsLoading && !activePlot && (
        <p className="text-sm text-muted-foreground">
          Diagnostic charts appear here after you select a capture from the timeline.
        </p>
      )}
    </div>
  );
}

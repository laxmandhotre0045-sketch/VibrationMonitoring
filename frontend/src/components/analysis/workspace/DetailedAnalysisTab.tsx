import React, { useMemo } from "react";
import { Activity, BarChart3, Layers } from "lucide-react";
import type { PlotSeries, PlotType, SensorDataUpload } from "@/types/measurements";
import { PLOT_LABELS } from "@/types/measurements";
import { DiagnosticChart } from "@/components/analysis/DiagnosticChart";
import { AnalysisSummaryPanel } from "@/components/analysis/AnalysisSummaryPanel";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { AdvancedPlotsSection } from "./AdvancedPlotsSection";
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

/**
 * The Waveform section, as an outline.
 *
 * All five plots arrive in one `getAllPlots` response, so a selector that
 * showed one at a time was hiding four charts that were already loaded. Each
 * group pairs a waveform with the spectrum derived from it — time waveform with
 * its FFT, circular waveform with its envelope — which is the pairing an
 * analyst reads together; the trend plot stands on its own.
 */
const WAVEFORM_GROUPS: { key: string; title: string; types: PlotType[] }[] = [
  { key: "A", title: "Time Waveform", types: ["time_waveform", "fft_spectrum"] },
  {
    key: "B",
    title: "Circular Time Waveform",
    types: ["circular_time_waveform", "envelope_spectrum"],
  },
  { key: "C", title: "Trend Plot", types: ["trend_plot"] },
];

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
  plotSource,
  selectedUploadId,
  selectedBaselineId,
}: DetailedAnalysisTabProps) {
  const plotsByType = useMemo(() => {
    const map = new Map<PlotType, PlotSeries>();
    for (const plot of plotsData?.plots ?? []) {
      map.set(plot.plot_type, plot);
    }
    return map;
  }, [plotsData]);

  const hasAnyPlot = plotsByType.size > 0;

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

      {/* ── 1. Waveform ───────────────────────────────────────────────── */}
      <section className="space-y-g3">
        <AnalysisSectionHeader
          icon={Activity}
          title="1. Waveform"
          subtitle="Time and circular waveforms with their derived spectra, plus the capture trend."
        />

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

        {!hasAnyPlot && !plotsLoading && (
          <p className="text-sm text-muted-foreground">
            Waveform charts appear here after you select a capture from the timeline.
          </p>
        )}

        {hasAnyPlot &&
          WAVEFORM_GROUPS.map((group) => {
            const plots = group.types
              .map((type) => plotsByType.get(type))
              .filter((plot): plot is PlotSeries => !!plot);

            return (
              <div key={group.key} className="space-y-g2">
                <div className="flex items-baseline gap-g2">
                  <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border bg-warm text-xs font-bold text-signal-dark">
                    {group.key}
                  </span>
                  <h3 className="text-sm font-bold text-foreground">{group.title}</h3>
                </div>

                {plots.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Not returned for this capture on CH-{activeChannel + 1}.
                  </p>
                ) : (
                  <div className="space-y-g3">
                    {plots.map((plot) => (
                      <DiagnosticChart
                        key={`${plot.plot_type}-${plot.channel}-${plotSource}-${selectedUploadId}-${selectedBaselineId}`}
                        plot={plot}
                        height={GRAPH_PRIMARY_HEIGHT}
                        samplingRateHz={samplingRate}
                      />
                    ))}
                  </div>
                )}

                {plots.length > 0 && plots.length < group.types.length && (
                  <p className="text-sm text-muted-foreground">
                    {group.types
                      .filter((type) => !plotsByType.has(type))
                      .map((type) => PLOT_LABELS[type])
                      .join(", ")}{" "}
                    not returned for this capture.
                  </p>
                )}
              </div>
            );
          })}
      </section>

      {/* ── 2. Advanced Plots & Diagnostics ───────────────────────────── */}
      <section className="space-y-g3">
        <AnalysisSectionHeader
          icon={Layers}
          title="2. Advanced Plots & Diagnostics"
          subtitle="Select a diagnostic view — each one loads on demand for the selected sensor."
        />
        <AdvancedPlotsSection
          sensorId={sensorId}
          channelCount={plotChannelCount}
          activeChannel={activeChannel}
          selectedUploadId={selectedUploadId}
        />
      </section>
    </div>
  );
}

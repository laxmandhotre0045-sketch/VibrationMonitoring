import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Settings2, BarChart3, LineChart, Bookmark } from "lucide-react";
import { listEquipment, getEquipment } from "@/api/equipment";
import {
  createBaselineFromUpload,
  getBaselinePlots,
  getPrimaryBaseline,
  listBaselines,
} from "@/api/baselines";
import {
  getPlotConfig,
  savePlotConfig,
  uploadSensorPdf,
  listUploads,
  getAllPlots,
} from "@/api/measurements";
import { DiagnosticChart } from "@/components/analysis/DiagnosticChart";
import { PlotSelector } from "@/components/analysis/PlotSelector";
import { SaveBaselineModal } from "@/components/analysis/SaveBaselineModal";
import { CaptureTimelineSection } from "@/components/analysis/CaptureTimelineSection";
import { AnalysisSummaryPanel } from "@/components/analysis/AnalysisSummaryPanel";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisBodyStack,
  analysisCardPad,
  analysisGridGap,
  analysisInputClass,
  analysisPageStack,
  analysisSelectClass,
} from "@/components/analysis/analysis-layout";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { PageHero } from "@/components/layout/PageHero";
import { useAuth } from "@/contexts/AuthContext";
import { WRITE_ROLES } from "@/lib/role-access";
import { PLOT_TYPES, type PlotConfigInput, type PlotSeries, type PlotType, type SensorDataUpload } from "@/types/measurements";
import type { EquipmentOut } from "@/types/equipment";
import { cn } from "@/lib/utils";

type PlotSource = "upload" | "baseline";

const DIAGNOSTIC_CHART_HEIGHT = 480;

const selectClass = analysisSelectClass;

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString();
}

export function VibrationAnalysisPage() {
  const queryClient = useQueryClient();
  const [equipmentId, setEquipmentId] = useState("");
  const [sensorId, setSensorId] = useState("");
  const [channelCount, setChannelCount] = useState(2);
  const [activeChannel, setActiveChannel] = useState(0);
  const [samplingRate, setSamplingRate] = useState(25600);
  const [fftLines, setFftLines] = useState(1600);
  const [selectedUploadId, setSelectedUploadId] = useState("");
  const [selectedBaselineId, setSelectedBaselineId] = useState("");
  const [plotSource, setPlotSource] = useState<PlotSource>("upload");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [activePlotType, setActivePlotType] = useState<PlotType>("time_waveform");
  const [baselineModalOpen, setBaselineModalOpen] = useState(false);
  const [showAllBaselines, setShowAllBaselines] = useState(false);
  const [selectedUploadMeta, setSelectedUploadMeta] = useState<SensorDataUpload | null>(null);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);

  const { hasRole } = useAuth();
  const canWrite = hasRole(WRITE_ROLES);

  const { data: equipmentList } = useQuery({
    queryKey: ["equipment-list-analysis"],
    queryFn: () => listEquipment({ page: 1, page_size: 100 }),
  });

  const { data: equipment } = useQuery({
    queryKey: ["equipment-detail", equipmentId],
    queryFn: () => getEquipment(equipmentId),
    enabled: !!equipmentId,
  });

  const { data: plotConfig } = useQuery({
    queryKey: ["plot-config", sensorId],
    queryFn: () => getPlotConfig(sensorId),
    enabled: !!sensorId,
    retry: false,
  });

  const { data: uploads } = useQuery({
    queryKey: ["sensor-uploads", sensorId],
    queryFn: async () => (await listUploads(sensorId)).items,
    enabled: !!sensorId,
  });

  const { data: primaryBaseline } = useQuery({
    queryKey: ["primary-baseline", sensorId],
    queryFn: () => getPrimaryBaseline(sensorId),
    enabled: !!sensorId,
  });

  const { data: baselineList } = useQuery({
    queryKey: ["baseline-list", sensorId],
    queryFn: () => listBaselines(sensorId),
    enabled: !!sensorId,
  });

  const selectedUpload =
    selectedUploadMeta ?? uploads?.find((u) => u.id === selectedUploadId);
  const plotChannelCount =
    plotSource === "baseline"
      ? baselineList?.items.find((b) => b.id === selectedBaselineId)?.channel_count ?? channelCount
      : selectedUpload?.channel_count ?? channelCount;

  const plotsEnabled =
    plotSource === "upload" ? !!selectedUploadId : !!selectedBaselineId;

  const {
    data: plotsData,
    isLoading: plotsLoading,
    error: plotsError,
    refetch: refetchPlots,
  } = useQuery({
    queryKey: ["plots", plotSource, selectedUploadId, selectedBaselineId, activeChannel],
    queryFn: () =>
      plotSource === "baseline"
        ? getBaselinePlots(selectedBaselineId, activeChannel)
        : getAllPlots(selectedUploadId, activeChannel),
    enabled: plotsEnabled,
    retry: 1,
  });

  useEffect(() => {
    if (plotConfig) {
      setChannelCount(plotConfig.channel_count);
      setActiveChannel(Math.min(plotConfig.active_channel, plotConfig.channel_count - 1));
      setSamplingRate(plotConfig.sampling_rate_hz);
      setFftLines(plotConfig.fft_lines);
    }
  }, [plotConfig]);

  useEffect(() => {
    if (activeChannel >= plotChannelCount) {
      setActiveChannel(Math.max(0, plotChannelCount - 1));
    }
  }, [activeChannel, plotChannelCount]);

  const saveConfigMutation = useMutation({
    mutationFn: async () => {
      const payload: PlotConfigInput = {
        sensor_id: sensorId,
        channel_count: channelCount,
        active_channel: activeChannel,
        sampling_rate_hz: samplingRate,
        fft_lines: fftLines,
        enabled_plots: [...PLOT_TYPES],
      };
      return savePlotConfig(sensorId, payload, !!plotConfig);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plot-config", sensorId] });
      setStatusMsg("Plot configuration saved.");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const detail = err.response?.data?.detail;
      setStatusMsg(typeof detail === "string" ? detail : "Failed to save configuration.");
    },
  });

  const uploadMutation = useMutation({
    mutationFn: () => uploadSensorPdf(sensorId, channelCount, pdfFile!),
    onSuccess: (upload) => {
      queryClient.invalidateQueries({ queryKey: ["sensor-uploads", sensorId] });
      queryClient.invalidateQueries({ queryKey: ["sensor-uploads-timeline", sensorId] });
      setSelectedUploadId(upload.id);
      setSelectedUploadMeta(upload);
      setPlotSource("upload");
      setActiveChannel(0);
      setTimelineRefreshKey((k) => k + 1);
      queryClient.invalidateQueries({ queryKey: ["plots", "upload", upload.id] });
      setStatusMsg(`Data uploaded and parsed (${upload.sample_count ?? 0} samples). Loading plots...`);
      setPdfFile(null);
      setTimeout(() => refetchPlots(), 100);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setStatusMsg(err.response?.data?.detail || "Upload failed.");
    },
  });

  const saveBaselineMutation = useMutation({
    mutationFn: (payload: { name: string; description: string; setAsPrimary: boolean }) =>
      createBaselineFromUpload(selectedUploadId, {
        name: payload.name,
        description: payload.description || null,
        set_as_primary: payload.setAsPrimary,
        labels: [],
      }),
    onSuccess: (baseline) => {
      queryClient.invalidateQueries({ queryKey: ["baseline-list", sensorId] });
      queryClient.invalidateQueries({ queryKey: ["primary-baseline", sensorId] });
      setBaselineModalOpen(false);
      setStatusMsg(`Baseline saved: "${baseline.name}" (${baseline.sample_count} samples).`);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const detail = err.response?.data?.detail;
      setStatusMsg(typeof detail === "string" ? detail : "Failed to save baseline.");
    },
  });

  const sensors = (equipment as EquipmentOut | undefined)?.sensors ?? [];

  const plotsByType = useMemo(() => {
    const map = new Map<PlotType, PlotSeries>();
    for (const plot of plotsData?.plots ?? []) {
      map.set(plot.plot_type, plot);
    }
    return map;
  }, [plotsData]);

  const availablePlotTypes = useMemo(
    () => PLOT_TYPES.filter((type) => plotsByType.has(type)),
    [plotsByType]
  );

  const activePlot = plotsByType.get(activePlotType);
  const baselineDefaultName = selectedUpload
    ? `Baseline ${formatDateTime(selectedUpload.created_at)}`
    : "New baseline";

  useEffect(() => {
    if (availablePlotTypes.length === 0) return;
    if (!availablePlotTypes.includes(activePlotType)) {
      setActivePlotType(availablePlotTypes[0]);
    }
  }, [availablePlotTypes, activePlotType]);

  const handleTimelineSelect = (uploadId: string, upload?: SensorDataUpload) => {
    setSelectedUploadId(uploadId);
    if (upload) setSelectedUploadMeta(upload);
    setPlotSource("upload");
    setActiveChannel(0);
    queryClient.invalidateQueries({ queryKey: ["plots", "upload", uploadId] });
  };

  return (
    <div className={analysisPageStack}>
      <PageHero
        title="Vibration Analysis"
        subtitle="Time waveform, circular waveform, FFT, envelope, and trend plots for sensor diagnostics."
        vibrationBg
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Vibration Analysis" },
        ]}
      />

      {statusMsg && (
        <div className="rounded-md border border-border border-l-2 border-l-signal-light bg-warm px-4 py-2">
          <p className="text-base text-foreground">{statusMsg}</p>
        </div>
      )}

      <SaveBaselineModal
        open={baselineModalOpen}
        defaultName={baselineDefaultName}
        isSaving={saveBaselineMutation.isPending}
        onClose={() => setBaselineModalOpen(false)}
        onSave={(payload) => saveBaselineMutation.mutate(payload)}
      />

      <GlassCard className={analysisCardPad} delay={0.05}>
        <AnalysisSectionHeader icon={Settings2} title="1. Select Sensor & Configure" />
        <div className={analysisBodyStack}>
          <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
            <FormField label="Equipment" compact>
              <select
                className={selectClass}
                value={equipmentId}
                onChange={(e) => {
                  setEquipmentId(e.target.value);
                  setSensorId("");
                }}
              >
                <option value="">Select equipment...</option>
                {equipmentList?.items.map((eq) => (
                  <option key={eq.id} value={eq.id}>
                    {eq.machine_name} — {eq.plant_name}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Sensor" compact>
              <select
                className={selectClass}
                value={sensorId}
                onChange={(e) => {
                  setSensorId(e.target.value);
                  setSelectedUploadId("");
                  setSelectedUploadMeta(null);
                }}
                disabled={!equipmentId}
              >
                <option value="">Select sensor...</option>
                {sensors.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.sensor_type} — {s.mounting_location}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          {sensorId && (
            <div className="rounded-md border border-border bg-surface/60 px-3 py-2 space-y-1.5">
              <p className="text-sm font-semibold text-brand flex items-center gap-1.5">
                <Bookmark size={12} className="text-signal-dark" />
                Primary baseline
              </p>
              {primaryBaseline ? (
                <p className="text-sm text-foreground leading-snug">
                  <span className="font-semibold">{primaryBaseline.name}</span>
                  {" · "}
                  {formatDateTime(primaryBaseline.created_at)}
                  {" · "}
                  {primaryBaseline.sample_count} samples
                  {primaryBaseline.plot_count > 0 && (
                    <> · {primaryBaseline.plot_count} plots stored</>
                  )}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">No primary baseline set for this sensor.</p>
              )}
              {baselineList && baselineList.total > 0 && (
                <button
                  type="button"
                    className="text-sm font-medium text-signal-dark hover:underline"
                  onClick={() => setShowAllBaselines((v) => !v)}
                >
                  {showAllBaselines ? "Hide" : "View"} all baselines ({baselineList.total})
                </button>
              )}
              {showAllBaselines && baselineList && baselineList.items.length > 0 && (
                <ul className="mt-1 max-h-28 overflow-y-auto space-y-0.5 text-sm text-muted-foreground">
                  {baselineList.items.map((b) => (
                    <li key={b.id} className="flex items-center gap-2">
                      {b.is_primary && (
                        <span className="text-sm font-semibold text-signal-dark uppercase">Primary</span>
                      )}
                      <span>{b.name}</span>
                      <span>· {formatDateTime(b.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className={cn("grid grid-cols-2 lg:grid-cols-4", analysisGridGap)}>
            <FormField label="Channel Count" compact>
              <TextInput
                type="number"
                min={1}
                max={32}
                className={analysisInputClass}
                value={channelCount}
                onChange={(e) => {
                  const count = Number(e.target.value);
                  setChannelCount(count);
                  if (activeChannel >= count) setActiveChannel(Math.max(0, count - 1));
                }}
              />
            </FormField>
            <FormField label={`Active Channel (0–${Math.max(0, channelCount - 1)})`} compact>
              <TextInput
                type="number"
                min={0}
                max={Math.max(0, channelCount - 1)}
                className={analysisInputClass}
                value={activeChannel}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setActiveChannel(Math.min(v, Math.max(0, channelCount - 1)));
                }}
              />
            </FormField>
            <FormField label="Sampling Rate (Hz)" compact>
              <TextInput
                type="number"
                className={analysisInputClass}
                value={samplingRate}
                onChange={(e) => setSamplingRate(Number(e.target.value))}
              />
            </FormField>
            <FormField label="FFT Lines" compact>
              <TextInput
                type="number"
                className={analysisInputClass}
                value={fftLines}
                onChange={(e) => setFftLines(Number(e.target.value))}
              />
            </FormField>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-0.5">
            <Button
              size="sm"
              onClick={() => saveConfigMutation.mutate()}
              disabled={!sensorId || saveConfigMutation.isPending || !canWrite}
            >
              Save Plot Configuration
            </Button>
            {!canWrite && (
              <p className="text-sm text-muted-foreground">
                Read-only users cannot save plot configuration.
              </p>
            )}
            {plotConfig && (
              <p className="text-sm text-machine-healthy font-medium">
                Configuration exists for this sensor.
              </p>
            )}
          </div>
        </div>
      </GlassCard>

      <GlassCard className={analysisCardPad} delay={0.08}>
        <AnalysisSectionHeader icon={Upload} title="2. Upload Sensor Data" />
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            CSV or PDF with rows: timestamp_, ch0, ch1, ... and numeric values.
          </p>
          <div className="flex flex-col md:flex-row md:items-end gap-2">
            <FormField label="Data file" className="flex-1 min-w-0" compact>
              <input
                type="file"
                accept=".pdf,.csv,application/pdf,text/csv"
                className={cn(
                  "w-full text-base text-foreground file:mr-3 file:py-1.5 file:px-3",
                  "file:rounded-md file:border file:border-border file:bg-white",
                  "file:text-base file:font-medium file:text-foreground",
                  "file:cursor-pointer hover:file:bg-warm"
                )}
                disabled={!sensorId || !canWrite}
                onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
              />
            </FormField>
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={!sensorId || !pdfFile || uploadMutation.isPending || !canWrite}
              className="shrink-0"
            >
              Upload Data File
            </Button>
          </div>
          {!canWrite && (
            <p className="text-sm text-muted-foreground">
              Read-only users cannot upload sensor data.
            </p>
          )}
        </div>
      </GlassCard>

      <CaptureTimelineSection
        sensorId={sensorId}
        selectedUploadId={selectedUploadId}
        refreshKey={timelineRefreshKey}
        onSelectUpload={handleTimelineSelect}
      />

      <GlassCard className={analysisCardPad} delay={0.14}>
        <AnalysisSectionHeader icon={BarChart3} title="4. Analysis" />
        <div className={cn("grid lg:grid-cols-2", analysisGridGap)}>
          <AnalysisSummaryPanel
            selectedUpload={plotSource === "upload" ? selectedUpload : undefined}
            plotChannelCount={plotChannelCount}
            activeChannel={activeChannel}
            onChannelChange={setActiveChannel}
            canWrite={canWrite}
            onSaveBaseline={() => setBaselineModalOpen(true)}
            saveBaselineDisabled={saveBaselineMutation.isPending || !selectedUploadId}
          />
          <div className="space-y-3">
            {sensorId && baselineList && baselineList.total > 0 && (
              <div className="rounded-md border border-border bg-surface/50 px-3 py-2 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Comparison Source
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    className={cn(selectClass, "w-auto min-w-[130px]")}
                    value={plotSource}
                    onChange={(e) => {
                      const next = e.target.value as PlotSource;
                      setPlotSource(next);
                      setActiveChannel(0);
                      if (next === "baseline" && !selectedBaselineId && baselineList.items[0]) {
                        setSelectedBaselineId(baselineList.items[0].id);
                      }
                    }}
                  >
                    <option value="upload">Timeline capture</option>
                    <option value="baseline">Saved baseline</option>
                  </select>
                  {plotSource === "baseline" && (
                    <select
                      className={cn(selectClass, "w-auto min-w-[160px]")}
                      value={selectedBaselineId}
                      onChange={(e) => {
                        setSelectedBaselineId(e.target.value);
                        setActiveChannel(0);
                      }}
                    >
                      <option value="">Select baseline...</option>
                      {baselineList.items.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                          {b.is_primary ? " (primary)" : ""}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            )}
            {plotsEnabled && plotsData && plotsData.plots.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                  Plot Type
                </p>
                <PlotSelector
                  value={activePlotType}
                  onChange={setActivePlotType}
                  availableTypes={availablePlotTypes}
                  compact
                />
              </div>
            )}
            {plotsLoading && <p className="text-sm text-muted-foreground">Loading analysis data…</p>}
            {plotsError && (
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
      </GlassCard>

      <GlassCard className={analysisCardPad} delay={0.16}>
        <AnalysisSectionHeader icon={LineChart} title="5. Visualization" />
        {!plotsEnabled && !plotsLoading && (
          <p className="text-sm text-muted-foreground mb-2">
            Diagnostic charts appear here after you select a capture from the timeline.
          </p>
        )}
        {activePlot && (
          <div className="w-full">
            <DiagnosticChart
              key={`${activePlot.plot_type}-${activePlot.channel}-${plotSource}-${selectedUploadId}-${selectedBaselineId}`}
              plot={activePlot}
              height={DIAGNOSTIC_CHART_HEIGHT}
              samplingRateHz={samplingRate}
            />
          </div>
        )}
      </GlassCard>
    </div>
  );
}

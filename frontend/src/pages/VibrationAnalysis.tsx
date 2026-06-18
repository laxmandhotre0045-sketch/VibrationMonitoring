import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Settings2, BarChart3, Bookmark, type LucideIcon } from "lucide-react";
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
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { PageHero } from "@/components/layout/PageHero";
import { useAuth } from "@/contexts/AuthContext";
import { WRITE_ROLES } from "@/lib/role-access";
import { PLOT_TYPES, type PlotConfigInput, type PlotSeries, type PlotType } from "@/types/measurements";
import type { EquipmentOut } from "@/types/equipment";
import { cn } from "@/lib/utils";

type PlotSource = "upload" | "baseline";

const DIAGNOSTIC_CHART_HEIGHT = 600;

const selectClass = cn(
  "w-full px-4 py-3 text-base font-normal rounded-lg transition-colors appearance-none cursor-pointer",
  "bg-white text-foreground border border-border",
  "focus:outline-none focus:border-signal-light focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);

function CardHeader({
  icon: Icon,
  title,
}: {
  icon: LucideIcon;
  title: string;
}) {
  return (
    <div className="flex items-center gap-3 mb-6 pb-4 border-b border-border">
      <span className="w-10 h-10 rounded-lg bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0">
        <Icon size={15} />
      </span>
      <h2 className="text-section-title">{title}</h2>
    </div>
  );
}

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
    queryFn: () => listUploads(sensorId),
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

  const selectedUpload = uploads?.find((u) => u.id === selectedUploadId);
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
      setSelectedUploadId(upload.id);
      setPlotSource("upload");
      setActiveChannel(0);
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

  return (
    <div className="space-y-8">
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
        <div className="rounded-lg border border-border border-l-2 border-l-signal-light bg-warm px-5 py-3">
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

      <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
        <GlassCard className="p-6" delay={0.05}>
          <CardHeader icon={Settings2} title="1. Select Sensor & Configure" />
          <div className="space-y-6">
            <FormField label="Equipment">
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

            <FormField label="Sensor">
              <select
                className={selectClass}
                value={sensorId}
                onChange={(e) => setSensorId(e.target.value)}
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

            {sensorId && (
              <div className="rounded-lg border border-border bg-surface/60 px-4 py-3 space-y-2">
                <p className="text-sm font-semibold text-brand flex items-center gap-2">
                  <Bookmark size={14} className="text-signal-dark" />
                  Primary baseline
                </p>
                {primaryBaseline ? (
                  <p className="text-sm text-foreground">
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
                  <ul className="mt-2 max-h-36 overflow-y-auto space-y-1 text-sm text-muted-foreground">
                    {baselineList.items.map((b) => (
                      <li key={b.id} className="flex items-center gap-2">
                        {b.is_primary && (
                          <span className="text-xs font-semibold text-signal-dark uppercase">Primary</span>
                        )}
                        <span>{b.name}</span>
                        <span>· {formatDateTime(b.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <FormField label="Channel Count">
                <TextInput
                  type="number"
                  min={1}
                  max={32}
                  value={channelCount}
                  onChange={(e) => {
                    const count = Number(e.target.value);
                    setChannelCount(count);
                    if (activeChannel >= count) setActiveChannel(Math.max(0, count - 1));
                  }}
                />
              </FormField>
              <FormField label={`Active Channel (0–${Math.max(0, channelCount - 1)})`}>
                <TextInput
                  type="number"
                  min={0}
                  max={Math.max(0, channelCount - 1)}
                  value={activeChannel}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setActiveChannel(Math.min(v, Math.max(0, channelCount - 1)));
                  }}
                />
              </FormField>
              <FormField label="Sampling Rate (Hz)">
                <TextInput
                  type="number"
                  value={samplingRate}
                  onChange={(e) => setSamplingRate(Number(e.target.value))}
                />
              </FormField>
              <FormField label="FFT Lines">
                <TextInput
                  type="number"
                  value={fftLines}
                  onChange={(e) => setFftLines(Number(e.target.value))}
                />
              </FormField>
            </div>

            <Button
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
              <p className="text-helper text-machine-healthy font-medium">
                Configuration exists for this sensor.
              </p>
            )}
          </div>
        </GlassCard>

        <GlassCard className="p-6" delay={0.1}>
          <CardHeader icon={Upload} title="2. Upload Sensor Data" />
          <div className="space-y-6">
            <p className="text-helper">
              CSV or PDF with rows: timestamp_, ch0, ch1, ... and numeric values.
            </p>
            <FormField label="Data file">
              <input
                type="file"
                accept=".pdf,.csv,application/pdf,text/csv"
                className={cn(
                  "w-full text-base text-foreground file:mr-4 file:py-2 file:px-4",
                  "file:rounded-lg file:border file:border-border file:bg-white",
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
            >
              Upload Data File
            </Button>
            {!canWrite && (
              <p className="text-sm text-muted-foreground">
                Read-only users cannot upload sensor data or save baselines.
              </p>
            )}

            {uploads && uploads.length > 0 && (
              <FormField label="Previous uploads">
                <select
                  className={selectClass}
                  value={selectedUploadId}
                  onChange={(e) => {
                    setSelectedUploadId(e.target.value);
                    setPlotSource("upload");
                    setActiveChannel(0);
                  }}
                >
                  <option value="">Select upload...</option>
                  {uploads.map((u) => (
                    <option key={u.id} value={u.id}>
                      {formatDateTime(u.created_at)} — {u.sample_count ?? 0} samples ({u.parse_status})
                    </option>
                  ))}
                </select>
              </FormField>
            )}

            {selectedUploadId && selectedUpload?.parse_status === "parsed" && canWrite && (
              <Button
                variant="secondary"
                icon={<Bookmark size={16} />}
                onClick={() => setBaselineModalOpen(true)}
                disabled={saveBaselineMutation.isPending}
              >
                Save as baseline
              </Button>
            )}
          </div>
        </GlassCard>
      </div>

      <GlassCard className="p-6" delay={0.15}>
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-lg bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0">
              <BarChart3 size={15} />
            </span>
            <h2 className="text-section-title">3. Diagnostic Plots</h2>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {sensorId && baselineList && baselineList.total > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-muted-foreground">Source:</span>
                <select
                  className={cn(selectClass, "w-auto min-w-[140px] py-2 text-sm")}
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
                  <option value="upload">Current upload</option>
                  <option value="baseline">Saved baseline</option>
                </select>
                {plotSource === "baseline" && (
                  <select
                    className={cn(selectClass, "w-auto min-w-[180px] py-2 text-sm")}
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
            )}
            {plotsEnabled && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold text-muted-foreground">View channel:</span>
                {Array.from({ length: plotChannelCount }, (_, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setActiveChannel(i)}
                    className={cn(
                      "rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
                      activeChannel === i
                        ? "bg-cta text-cta-foreground"
                        : "border border-border bg-white text-muted-foreground hover:bg-surface"
                    )}
                  >
                    ch{i}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {plotsEnabled && plotsData && plotsData.plots.length > 0 && (
          <div className="mb-5">
            <PlotSelector
              value={activePlotType}
              onChange={setActivePlotType}
              availableTypes={availablePlotTypes}
            />
          </div>
        )}
        {plotsLoading && <p className="text-helper">Loading plots...</p>}
        {plotsError && (
          <p className="text-base text-destructive font-semibold">
            Failed to load plots:{" "}
            {(plotsError as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              "Try another channel or re-upload the file."}
          </p>
        )}
        {!plotsEnabled && !plotsLoading && (
          <p className="text-helper">
            Upload a file, select a previous upload, or choose a saved baseline to view plots.
          </p>
        )}
        {plotsEnabled && plotsData && plotsData.plots.length === 0 && !plotsLoading && (
          <p className="text-base font-semibold text-signal-dark">
            No plots returned. Try channel ch0 or check plot configuration.
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

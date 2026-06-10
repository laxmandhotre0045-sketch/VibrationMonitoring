import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Settings2, BarChart3, type LucideIcon } from "lucide-react";
import { listEquipment, getEquipment } from "@/api/equipment";
import {
  getPlotConfig,
  savePlotConfig,
  uploadSensorPdf,
  listUploads,
  getAllPlots,
} from "@/api/measurements";
import { DiagnosticChart } from "@/components/analysis/DiagnosticChart";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { PageHero } from "@/components/layout/PageHero";
import { PLOT_TYPES, type PlotConfigInput } from "@/types/measurements";
import type { EquipmentOut } from "@/types/equipment";
import { cn } from "@/lib/utils";

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

export function VibrationAnalysisPage() {
  const queryClient = useQueryClient();
  const [equipmentId, setEquipmentId] = useState("");
  const [sensorId, setSensorId] = useState("");
  const [channelCount, setChannelCount] = useState(2);
  const [activeChannel, setActiveChannel] = useState(0);
  const [samplingRate, setSamplingRate] = useState(25600);
  const [fftLines, setFftLines] = useState(1600);
  const [selectedUploadId, setSelectedUploadId] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [statusMsg, setStatusMsg] = useState("");

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

  const {
    data: plotsData,
    isLoading: plotsLoading,
    error: plotsError,
    refetch: refetchPlots,
  } = useQuery({
    queryKey: ["plots", selectedUploadId, activeChannel],
    queryFn: () => getAllPlots(selectedUploadId, activeChannel),
    enabled: !!selectedUploadId,
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
      queryClient.invalidateQueries({ queryKey: ["plots", upload.id] });
      setStatusMsg(`Data uploaded and parsed (${upload.sample_count ?? 0} samples). Loading plots...`);
      setPdfFile(null);
      setTimeout(() => refetchPlots(), 100);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setStatusMsg(err.response?.data?.detail || "Upload failed.");
    },
  });

  const sensors = (equipment as EquipmentOut | undefined)?.sensors ?? [];

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
              disabled={!sensorId || saveConfigMutation.isPending}
            >
              Save Plot Configuration
            </Button>
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
                disabled={!sensorId}
                onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
              />
            </FormField>
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={!sensorId || !pdfFile || uploadMutation.isPending}
            >
              Upload Data File
            </Button>

            {uploads && uploads.length > 0 && (
              <FormField label="Previous uploads">
                <select
                  className={selectClass}
                  value={selectedUploadId}
                  onChange={(e) => setSelectedUploadId(e.target.value)}
                >
                  <option value="">Select upload...</option>
                  {uploads.map((u) => (
                    <option key={u.id} value={u.id}>
                      {new Date(u.created_at).toLocaleString()} — {u.sample_count ?? 0} samples ({u.parse_status})
                    </option>
                  ))}
                </select>
              </FormField>
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
            <h2 className="text-section-title">3. Diagnostic Plots (5)</h2>
          </div>
          {selectedUploadId && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold text-muted-foreground">View channel:</span>
              {Array.from({ length: channelCount }, (_, i) => (
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

        {selectedUploadId && (
          <p className="text-helper mb-4">
            Showing all 5 plots for <span className="font-semibold text-foreground">ch{activeChannel}</span>.
            Click ch0–ch{channelCount - 1} to switch.
          </p>
        )}
        {plotsLoading && <p className="text-helper">Generating plots...</p>}
        {plotsError && (
          <p className="text-base text-destructive font-semibold">
            Failed to load plots:{" "}
            {(plotsError as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              "Unknown error. Set Active Channel to 0–7 (ch0 = first channel)."}
          </p>
        )}
        {!selectedUploadId && !plotsLoading && (
          <p className="text-helper">Upload a file or select a previous upload to view plots.</p>
        )}
        {plotsData && plotsData.plots.length === 0 && (
          <p className="text-base font-semibold text-signal-dark">
            No plots returned. Check plot configuration and active channel.
          </p>
        )}
        {plotsData && plotsData.plots.length > 0 && (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {plotsData.plots.map((plot) => (
              <DiagnosticChart key={plot.plot_type} plot={plot} />
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

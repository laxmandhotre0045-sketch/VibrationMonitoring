import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Upload, Settings2 } from "lucide-react";
import { listEquipment, getEquipment } from "@/api/equipment";
import {
  getPlotConfig,
  savePlotConfig,
  uploadSensorPdf,
  listUploads,
  getAllPlots,
} from "@/api/measurements";
import { PlotChart } from "@/components/analysis/PlotChart";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { PLOT_TYPES, type PlotConfigInput } from "@/types/measurements";
import type { EquipmentOut } from "@/types/equipment";

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
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Activity className="h-7 w-7 text-blue-600" />
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Vibration Analysis</h1>
          <p className="text-sm text-slate-500">
            Time waveform, circular waveform, FFT, envelope, and trend plots.
          </p>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-800">
          {statusMsg}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <GlassCard>
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3 mb-4">
            <Settings2 className="h-4 w-4 text-slate-500" />
            <h2 className="font-semibold text-slate-800">1. Select Sensor &amp; Configure</h2>
          </div>
          <div className="space-y-3">
            <label className="block text-xs font-medium text-slate-600">Equipment</label>
            <select
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
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

            <label className="block text-xs font-medium text-slate-600">Sensor</label>
            <select
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
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

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600">Channel Count</label>
                <input
                  type="number"
                  min={1}
                  max={32}
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                  value={channelCount}
                  onChange={(e) => {
                    const count = Number(e.target.value);
                    setChannelCount(count);
                    if (activeChannel >= count) setActiveChannel(Math.max(0, count - 1));
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">Active Channel (0–{Math.max(0, channelCount - 1)})</label>
                <input
                  type="number"
                  min={0}
                  max={Math.max(0, channelCount - 1)}
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                  value={activeChannel}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setActiveChannel(Math.min(v, Math.max(0, channelCount - 1)));
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">Sampling Rate (Hz)</label>
                <input
                  type="number"
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                  value={samplingRate}
                  onChange={(e) => setSamplingRate(Number(e.target.value))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">FFT Lines</label>
                <input
                  type="number"
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                  value={fftLines}
                  onChange={(e) => setFftLines(Number(e.target.value))}
                />
              </div>
            </div>

            <Button
              onClick={() => saveConfigMutation.mutate()}
              disabled={!sensorId || saveConfigMutation.isPending}
            >
              Save Plot Configuration
            </Button>
            {plotConfig && (
              <p className="text-xs text-green-600">Configuration exists for this sensor.</p>
            )}
          </div>
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3 mb-4">
            <Upload className="h-4 w-4 text-slate-500" />
            <h2 className="font-semibold text-slate-800">2. Upload Sensor Data</h2>
          </div>
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              CSV or PDF with rows: timestamp_, ch0, ch1, ... and numeric values.
            </p>
            <input
              type="file"
              accept=".pdf,.csv,application/pdf,text/csv"
              className="w-full text-sm"
              disabled={!sensorId}
              onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
            />
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={!sensorId || !pdfFile || uploadMutation.isPending}
            >
              Upload Data File
            </Button>

            {uploads && uploads.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Previous uploads</label>
                <select
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
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
              </div>
            )}
          </div>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold text-slate-800">3. Diagnostic Plots (5)</h2>
          {selectedUploadId && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-slate-600">View channel:</span>
              {Array.from({ length: channelCount }, (_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setActiveChannel(i)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    activeChannel === i
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  ch{i}
                </button>
              ))}
            </div>
          )}
        </div>
        {selectedUploadId && (
          <p className="mb-3 text-xs text-slate-500">
            Showing all 5 plots for <strong>ch{activeChannel}</strong>. Click ch0–ch{channelCount - 1} to switch.
          </p>
        )}
        {plotsLoading && <p className="text-sm text-slate-500">Generating plots...</p>}
        {plotsError && (
          <p className="text-sm text-red-600">
            Failed to load plots:{" "}
            {(plotsError as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              "Unknown error. Set Active Channel to 0–7 (ch0 = first channel)."}
          </p>
        )}
        {!selectedUploadId && !plotsLoading && (
          <p className="text-sm text-slate-500">Upload a file or select a previous upload to view plots.</p>
        )}
        {plotsData && plotsData.plots.length === 0 && (
          <p className="text-sm text-amber-600">No plots returned. Check plot configuration and active channel.</p>
        )}
        {plotsData && plotsData.plots.length > 0 && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {plotsData.plots.map((plot) => (
              <PlotChart key={plot.plot_type} plot={plot} />
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

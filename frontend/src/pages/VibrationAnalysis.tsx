import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Settings2, Trash2 } from "lucide-react";
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
import { CaptureTimelineSection } from "@/components/analysis/CaptureTimelineSection";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { AnalysisWorkspace } from "@/components/analysis/workspace/AnalysisWorkspace";
import { BaselineManagementPanel } from "@/components/analysis/baseline/BaselineManagementPanel";
import { SelectedCapturePanel } from "@/components/analysis/workspace/SelectedCapturePanel";
import { StatusHealthTab } from "@/components/analysis/health/StatusHealthTab";
import { TrendAnalysisTab } from "@/components/analysis/workspace/TrendAnalysisTab";
import { DetailedAnalysisTab } from "@/components/analysis/workspace/DetailedAnalysisTab";
import { StatisticsTab } from "@/components/analysis/workspace/StatisticsTab";
import { SaveBaselineModal } from "@/components/analysis/SaveBaselineModal";
import {
  analysisCardPad,
  analysisGridGap,
  analysisPageStack,
  analysisSelectClass,
} from "@/components/analysis/analysis-layout";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { PageHero } from "@/components/layout/PageHero";
import { useAuth } from "@/contexts/AuthContext";
import { WRITE_ROLES } from "@/lib/role-access";
import type { AnalysisTabId } from "@/types/analysis-tabs";
import { PLOT_TYPES, type PlotConfigInput, type PlotSeries, type PlotType, type SensorDataUpload } from "@/types/measurements";
import type { EquipmentOut } from "@/types/equipment";
import { cn } from "@/lib/utils";

type PlotSource = "upload" | "baseline";

/**
 * Loaded on demand — this tab pulls in echarts-gl (WebGL), which no other view needs.
 * Keeps it out of the initial bundle.
 */
const WaterfallTab = React.lazy(() =>
  import("@/components/analysis/workspace/WaterfallTab").then((m) => ({
    default: m.WaterfallTab,
  }))
);

/** Lazy for the same reason: only this tab needs the polar chart code. */
const VectorTab = React.lazy(() =>
  import("@/components/analysis/workspace/VectorTab").then((m) => ({
    default: m.VectorTab,
  }))
);

const OrbitTab = React.lazy(() =>
  import("@/components/analysis/workspace/OrbitTab").then((m) => ({
    default: m.OrbitTab,
  }))
);

const MigrationTab = React.lazy(() =>
  import("@/components/analysis/workspace/MigrationTab").then((m) => ({
    default: m.MigrationTab,
  }))
);

const selectClass = analysisSelectClass;

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activePlotType, setActivePlotType] = useState<PlotType>("time_waveform");
  const [baselineModalOpen, setBaselineModalOpen] = useState(false);
  const [selectedUploadMeta, setSelectedUploadMeta] = useState<SensorDataUpload | null>(null);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const [activeTab, setActiveTab] = useState<AnalysisTabId>("detailed");

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

  const {
    data: baselineList,
    isLoading: baselineListLoading,
    error: baselineListError,
    refetch: refetchBaselineList,
  } = useQuery({
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
      queryClient.invalidateQueries({ queryKey: ["upload-factor-trends", upload.id] });
      queryClient.invalidateQueries({ queryKey: ["upload-features", upload.id] });
      setActiveTab("trend");
      setPdfFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setTimeout(() => refetchPlots(), 100);
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
    },
  });

  const sensors = (equipment as EquipmentOut | undefined)?.sensors ?? [];

  const handleRemoveFile = () => {
    setPdfFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

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
    queryClient.invalidateQueries({ queryKey: ["upload-factor-trends", uploadId] });
    queryClient.invalidateQueries({ queryKey: ["upload-features", uploadId] });
  };

  const handleLoadBaseline = (baseline: { id: string }) => {
    setPlotSource("baseline");
    setSelectedBaselineId(baseline.id);
    setActiveChannel(0);
    queryClient.invalidateQueries({ queryKey: ["plots", "baseline", baseline.id] });
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

      <SaveBaselineModal
        open={baselineModalOpen}
        defaultName={baselineDefaultName}
        isSaving={saveBaselineMutation.isPending}
        onClose={() => setBaselineModalOpen(false)}
        onSave={(payload) => saveBaselineMutation.mutate(payload)}
      />

      <GlassCard className={analysisCardPad} delay={0.05}>
        <AnalysisSectionHeader
          icon={Settings2}
          title="Equipment & Sensor"
          subtitle="Select equipment and sensor for all analysis views."
        />
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
      </GlassCard>

      <BaselineManagementPanel
        sensorId={sensorId}
        baselineList={baselineList}
        isLoading={baselineListLoading}
        error={baselineListError}
        onRetry={() => void refetchBaselineList()}
        selectedBaselineId={selectedBaselineId}
        loadedBaselineId={plotSource === "baseline" ? selectedBaselineId : ""}
        onLoadBaseline={handleLoadBaseline}
        formatDateTime={formatDateTime}
        canWrite={canWrite}
      />

      <GlassCard className={analysisCardPad} delay={0.08}>
        <AnalysisSectionHeader icon={Upload} title="Upload Sensor Data" />
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            CSV or PDF with rows: timestamp_, ch0, ch1, ... and numeric values.
          </p>
          <div className="flex flex-col md:flex-row md:items-end gap-2">
            {!pdfFile ? (
              <FormField label="Data file" className="flex-1 min-w-0" compact>
                <input
                  ref={fileInputRef}
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
            ) : (
              <div
                className={cn(
                  "flex flex-1 min-w-0 items-center justify-between gap-3 rounded-lg border border-border",
                  "border-l-2 border-l-signal-light bg-white px-4 py-3"
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{pdfFile.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {formatFileSize(pdfFile.size)}
                    {pdfFile.type ? ` · ${pdfFile.type}` : ""}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 size={14} />}
                  onClick={handleRemoveFile}
                  disabled={uploadMutation.isPending}
                  className="shrink-0"
                >
                  Remove File
                </Button>
              </div>
            )}
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

      <SelectedCapturePanel selectedUpload={plotSource === "upload" ? selectedUpload : undefined} />

      <AnalysisWorkspace activeTab={activeTab} onTabChange={setActiveTab}>
        <div hidden={activeTab !== "health"}>
          <StatusHealthTab
            sensorId={sensorId}
            selectedUploadId={selectedUploadId}
            channelCount={plotChannelCount}
            primaryBaseline={primaryBaseline}
            baselineList={baselineList?.items}
          />
        </div>
        <div hidden={activeTab !== "trend"}>
          <TrendAnalysisTab selectedUploadId={selectedUploadId} />
        </div>
        <div hidden={activeTab !== "detailed"}>
          <DetailedAnalysisTab
            selectedUpload={plotSource === "upload" ? selectedUpload : undefined}
            plotChannelCount={plotChannelCount}
            activeChannel={activeChannel}
            onChannelChange={setActiveChannel}
            channelCount={channelCount}
            onChannelCountChange={(count) => {
              setChannelCount(count);
              if (activeChannel >= count) setActiveChannel(Math.max(0, count - 1));
            }}
            samplingRate={samplingRate}
            onSamplingRateChange={setSamplingRate}
            fftLines={fftLines}
            onFftLinesChange={setFftLines}
            canWrite={canWrite}
            sensorId={sensorId}
            onSaveConfig={() => saveConfigMutation.mutate()}
            saveConfigPending={saveConfigMutation.isPending}
            plotConfigExists={!!plotConfig}
            onSaveBaseline={() => setBaselineModalOpen(true)}
            saveBaselineDisabled={saveBaselineMutation.isPending || !selectedUploadId}
            plotsEnabled={plotsEnabled}
            plotsLoading={plotsLoading}
            plotsError={plotsError}
            plotsData={plotsData}
            availablePlotTypes={availablePlotTypes}
            activePlotType={activePlotType}
            onPlotTypeChange={setActivePlotType}
            activePlot={activePlot}
            plotSource={plotSource}
            selectedUploadId={selectedUploadId}
            selectedBaselineId={selectedBaselineId}
          />
        </div>
        <div hidden={activeTab !== "waterfall"}>
          {activeTab === "waterfall" && (
            <React.Suspense
              fallback={
                <p className="text-sm text-muted-foreground">Loading 3D waterfall…</p>
              }
            >
              <WaterfallTab
                sensorId={sensorId}
                channelCount={plotChannelCount}
                defaultChannel={activeChannel}
              />
            </React.Suspense>
          )}
        </div>
        <div hidden={activeTab !== "vector"}>
          {activeTab === "vector" && (
            <React.Suspense
              fallback={
                <p className="text-sm text-muted-foreground">Loading vibration vector…</p>
              }
            >
              <VectorTab
                selectedUploadId={selectedUploadId}
                sensorId={sensorId}
                channelCount={plotChannelCount}
                defaultChannel={activeChannel}
              />
            </React.Suspense>
          )}
        </div>
        <div hidden={activeTab !== "orbit"}>
          {activeTab === "orbit" && (
            <React.Suspense
              fallback={<p className="text-sm text-muted-foreground">Loading casing orbit…</p>}
            >
              <OrbitTab
                selectedUploadId={selectedUploadId}
                sensorId={sensorId}
                channelCount={plotChannelCount}
              />
            </React.Suspense>
          )}
        </div>
        <div hidden={activeTab !== "migration"}>
          {activeTab === "migration" && (
            <React.Suspense
              fallback={<p className="text-sm text-muted-foreground">Calculating 1× response…</p>}
            >
              <MigrationTab sensorId={sensorId} channelCount={plotChannelCount} />
            </React.Suspense>
          )}
        </div>
        <div hidden={activeTab !== "statistics"}>
          <StatisticsTab
            plotsData={plotsData}
            samplingRateHz={samplingRate}
            activeChannel={activeChannel}
            plotsEnabled={plotsEnabled}
            plotsLoading={plotsLoading}
          />
        </div>
      </AnalysisWorkspace>
    </div>
  );
}

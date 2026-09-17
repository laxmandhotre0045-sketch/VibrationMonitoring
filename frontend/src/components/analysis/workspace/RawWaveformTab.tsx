import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import { Loader2, Radio } from "lucide-react";
import { getRawAnalysis, getRawSamples, listRawSnapshots } from "@/api/measurements";
import { Button } from "@/components/ui/Button";
import { FormField } from "@/components/ui/FormField";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { EchartsGraphViewport, GraphWorkspace } from "@/components/charts";
import { analysisBodyStack, analysisSelectClass } from "@/components/analysis/analysis-layout";
import { resetChartZoom, zoomChart } from "@/lib/graph-interactions";
import { buildRawWaveformOption, formatSeconds } from "@/lib/raw-waveform-option";
import {
  RAW_WINDOW_SIZES,
  type RawAnalysisResponse,
  type RawSamplesResponse,
} from "@/types/raw-vibration";
import { buildFftSpectrumOption } from "@/lib/fft-spectrum-option";
import type { PlotSeries } from "@/types/measurements";
import { cn } from "@/lib/utils";

const CHART_HEIGHT = 520;

interface RawWaveformPlotProps {
  data: RawSamplesResponse;
  channel: number;
  onRefresh: () => void;
  isRefreshing: boolean;
}

function RawWaveformPlotInner({ data, channel, onRefresh, isRefreshing }: RawWaveformPlotProps) {
  const chartRef = useRef<ReactECharts>(null);
  const option = useMemo(() => buildRawWaveformOption({ data, channel }), [data, channel]);

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );
  const handleResize = useCallback(() => {
    const i = getInstance();
    if (i && !i.isDisposed()) i.resize();
  }, [getInstance]);

  const handleExport = useCallback(() => {
    const i = getInstance();
    if (!i || i.isDisposed()) return;
    const url = i.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#FFFDF8" });
    const a = document.createElement("a");
    a.download = `sensovibe-raw-ch${channel}-${data.upload_id.slice(0, 8)}.png`;
    a.href = url;
    a.click();
  }, [getInstance, channel, data.upload_id]);

  const span =
    data.samples.length > 1
      ? data.samples[data.samples.length - 1].timestamp_ - data.samples[0].timestamp_
      : 0;

  return (
    <GraphWorkspace
      title="Raw Vibration Waveform"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <strong className="text-brand">RAW</strong>
          <span>unprocessed samples — no FFT, filtering or averaging</span>
          <span aria-hidden>·</span>
          <span>CH{channel}</span>
        </span>
      }
      headerExtra={
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            `${(data.sampleRate / 1000).toFixed(1)} kSPS`,
            `${data.channelCount} channels`,
            `${data.returned.toLocaleString()} of ${data.total_samples.toLocaleString()} samples`,
            `window ${formatSeconds(span)}`,
          ].map((f) => (
            <span
              key={f}
              // No `uppercase` here: it turns the micro sign in "80.0 µs" into a Greek
              // capital Mu, which reads as "80.0 MS" — three orders of magnitude wrong.
              className={cn(
                "rounded border border-border bg-warm/40 px-1.5 py-0.5",
                "text-[11px] font-semibold tracking-wide text-muted-foreground"
              )}
            >
              {f}
            </span>
          ))}
        </div>
      }
      height={CHART_HEIGHT}
      variant="primary"
      hint="X = time (s) · Y = raw sample value · scroll to zoom, drag the slider to pan"
      statistics={
        <p className="text-[11px] text-muted-foreground">
          Sample Rate: {data.sampleRate.toLocaleString()} SPS · Channels: {data.channelCount} ·
          interval {formatSeconds(1 / data.sampleRate)} · captured{" "}
          {new Date(data.measured_at ?? data.captured_at).toLocaleString()}
          {data.device_id && <> · device {data.device_id}</>}
          {data.has_more && <> · more samples available beyond this window</>}
        </p>
      }
      onZoomIn={() => {
        const i = getInstance();
        if (i) zoomChart(i, "in");
      }}
      onZoomOut={() => {
        const i = getInstance();
        if (i) zoomChart(i, "out");
      }}
      onReset={() => {
        const i = getInstance();
        if (i) resetChartZoom(i);
      }}
      onExport={handleExport}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      onChartResize={handleResize}
      channelLabel={`CH${channel}`}
      toolbarActions={["zoomIn", "zoomOut", "reset", "refresh", "export", "fullscreen"]}
    >
      {({ height, isFullscreen }) => (
        <EchartsGraphViewport
          chartRef={chartRef}
          option={option}
          chartHeight={height}
          isFullscreen={isFullscreen}
        />
      )}
    </GraphWorkspace>
  );
}

const RawWaveformPlot = memo(RawWaveformPlotInner);


/**
 * Vibration amplitudes span many orders of magnitude, so a fixed decimal count
 * either loses small values or floods large ones. Switch to exponent notation
 * outside the range where plain decimals stay readable.
 */
function formatMetric(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  if (magnitude === 0) return "0";
  if (magnitude < 1e-3 || magnitude >= 1e5) return value.toExponential(3);
  return value.toFixed(magnitude < 1 ? 4 : 3);
}

/** One number in the Vibration Parameters row. */
function MetricTile({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: number;
  unit?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-white px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-bold leading-tight text-brand">
        {formatMetric(value)}
        {unit && <span className="ml-1 text-xs font-semibold text-muted-foreground">{unit}</span>}
      </p>
      {hint && <p className="text-[11px] leading-tight text-muted-foreground">{hint}</p>}
    </div>
  );
}

/**
 * Adapts the raw-analysis spectrum to the PlotSeries shape the shared FFT chart
 * builder expects, so the raw page renders with the same axes, tooltip and peak
 * marker as every other spectrum in the app.
 */
function spectrumToPlotSeries(analysis: RawAnalysisResponse): PlotSeries {
  return {
    plot_type: "fft_spectrum",
    title: "FFT Spectrum",
    x_label: "Frequency (Hz)",
    y_label: "Amplitude",
    x: analysis.spectrum.frequencies,
    y: analysis.spectrum.amplitudes,
    channel: analysis.channel,
    metadata: {
      plot_style: "line",
      sampling_rate_hz: analysis.sample_rate_hz,
      block_size: analysis.spectrum.block_size,
      averages: analysis.spectrum.averages,
      fft_lines: analysis.spectrum.line_count,
    },
  };
}

function FftSpectrumPanel({ analysis }: { analysis: RawAnalysisResponse }) {
  const chartRef = useRef<ReactECharts>(null);
  const option = useMemo(
    () => buildFftSpectrumOption(spectrumToPlotSeries(analysis), analysis.sample_rate_hz),
    [analysis]
  );
  return (
    <GraphWorkspace
      title="FFT Spectrum"
      subtitle={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span>
            {analysis.spectrum.line_count.toLocaleString()} lines · Δf{" "}
            {analysis.spectrum.frequency_resolution_hz.toFixed(3)} Hz · block{" "}
            {analysis.spectrum.block_size.toLocaleString()} · {analysis.spectrum.averages} averages
          </span>
        </span>
      }
      height={CHART_HEIGHT}
      hint="X = frequency (Hz) · Y = amplitude · scroll to zoom, drag the slider to pan"
      toolbarActions={["zoomIn", "zoomOut", "reset", "fullscreen"]}
      channelLabel={`CH${analysis.channel}`}
    >
      {({ height, isFullscreen }) => (
        <EchartsGraphViewport
          chartRef={chartRef}
          option={option}
          chartHeight={height}
          isFullscreen={isFullscreen}
        />
      )}
    </GraphWorkspace>
  );
}

interface RawWaveformTabProps {
  sensorId: string;
}

export function RawWaveformTab({ sensorId }: RawWaveformTabProps) {
  const [snapshotId, setSnapshotId] = useState("");
  const [channel, setChannel] = useState(0);
  const [windowSize, setWindowSize] = useState<number>(2500);
  const [offset, setOffset] = useState(0);

  const snapshots = useQuery({
    queryKey: ["raw-snapshots", sensorId],
    queryFn: () => listRawSnapshots(sensorId),
    enabled: !!sensorId,
  });

  const items = snapshots.data?.items ?? [];
  const activeId = snapshotId || items[0]?.upload_id || "";

  useEffect(() => {
    setOffset(0);
  }, [activeId, windowSize]);

  const samples = useQuery({
    queryKey: ["raw-samples", activeId, channel, windowSize, offset],
    queryFn: () =>
      getRawSamples({ uploadId: activeId, channels: [channel], limit: windowSize, offset }),
    enabled: !!activeId,
    staleTime: 60_000,
  });

  /**
   * Spectrum and statistics come from the backend, which runs the same FFT and
   * feature-extraction code as the other analysis tabs. Keyed on the snapshot
   * and channel only — the waveform window does not change them, because they
   * describe the whole capture rather than the visible slice.
   */
  const analysis = useQuery({
    queryKey: ["raw-analysis", activeId, channel],
    queryFn: () => getRawAnalysis({ uploadId: activeId, channel }),
    enabled: !!activeId,
    staleTime: 60_000,
    retry: false,
  });

  const data = samples.data;
  const channelCount = data?.channelCount ?? items[0]?.channel_count ?? 8;

  return (
    <div className={analysisBodyStack}>
      <AnalysisSectionHeader
        icon={Radio}
        title="Raw Vibration Data"
        subtitle="Unprocessed 25 kSPS samples exactly as received from the device, before any FFT or signal processing."
        className="mb-0 pb-0 border-b-0"
      />

      {!sensorId && (
        <p className="text-sm text-muted-foreground">
          Select an equipment and sensor above to view raw vibration data.
        </p>
      )}

      {sensorId && snapshots.isLoading && (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
          <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
          <p className="text-sm text-muted-foreground">Loading raw snapshots…</p>
        </div>
      )}

      {sensorId && !snapshots.isLoading && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-8 text-center">
          <h3 className="text-base font-bold text-foreground">No raw snapshots for this sensor</h3>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            Raw data is streamed directly by the acquisition device. Register this sensor&rsquo;s
            device ID with the data collector to begin receiving snapshots.
          </p>
        </div>
      )}

      {sensorId && items.length > 0 && (
        <>
          {/* ── Latest Acquisition ─────────────────────────────────────── */}
          {analysis.data && (
            <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-white p-g3 lg:grid-cols-5">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Captured
                </p>
                <p className="mt-0.5 text-sm font-bold text-brand">
                  {new Date(analysis.data.measured_at ?? analysis.data.captured_at).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Sensor / device
                </p>
                <p className="mt-0.5 text-sm font-bold text-brand">
                  {analysis.data.device_id ?? analysis.data.sensor_id.slice(0, 8)}
                </p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Channel
                </p>
                <p className="mt-0.5 text-sm font-bold text-brand">
                  CH{analysis.data.channel + 1}
                  {analysis.data.machine_axis && (
                    <span className="ml-1 text-xs font-semibold text-muted-foreground">
                      {analysis.data.machine_axis.toLowerCase()}
                    </span>
                  )}
                </p>
                {analysis.data.channel_label && (
                  <p className="text-[11px] text-muted-foreground">{analysis.data.channel_label}</p>
                )}
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Sample count
                </p>
                <p className="mt-0.5 text-sm font-bold text-brand">
                  {analysis.data.sample_count.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Sampling rate
                </p>
                <p className="mt-0.5 text-sm font-bold text-brand">
                  {analysis.data.sample_rate_hz.toLocaleString()} Hz
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <FormField label="Snapshot" compact>
              <select
                className={analysisSelectClass}
                value={activeId}
                onChange={(e) => setSnapshotId(e.target.value)}
              >
                {items.map((s) => (
                  <option key={s.upload_id} value={s.upload_id}>
                    {new Date(s.measured_at ?? s.captured_at).toLocaleString()} —{" "}
                    {(s.sample_count ?? 0).toLocaleString()} samples
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Channel" compact>
              <select
                className={analysisSelectClass}
                value={channel}
                onChange={(e) => setChannel(Number(e.target.value))}
              >
                {Array.from({ length: channelCount }, (_, i) => (
                  <option key={i} value={i}>
                    CH{i}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Samples shown" compact>
              <select
                className={analysisSelectClass}
                value={windowSize}
                onChange={(e) => setWindowSize(Number(e.target.value))}
              >
                {RAW_WINDOW_SIZES.map((n) => (
                  <option key={n} value={n}>
                    {n.toLocaleString()}
                  </option>
                ))}
              </select>
            </FormField>

            <div className="flex items-end gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="flex-1"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - windowSize))}
              >
                ◀ Prev
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="flex-1"
                disabled={!data?.has_more}
                onClick={() => setOffset((o) => o + windowSize)}
              >
                Next ▶
              </Button>
            </div>
          </div>

          {samples.isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">Loading raw samples…</p>
            </div>
          )}

          {!samples.isLoading && samples.isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4">
              <p className="text-sm font-semibold text-destructive">
                {(samples.error as { response?: { data?: { detail?: string } } })?.response?.data
                  ?.detail ?? "Unable to load raw samples."}
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() => void samples.refetch()}
              >
                Retry
              </Button>
            </div>
          )}

          {!samples.isLoading && !samples.isError && data && data.samples.length > 0 && (
            <RawWaveformPlot
              data={data}
              channel={channel}
              onRefresh={() => void samples.refetch()}
              isRefreshing={samples.isFetching}
            />
          )}


          {/* ── FFT Spectrum ───────────────────────────────────────────── */}
          {analysis.isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">Computing spectrum and statistics…</p>
            </div>
          )}

          {!analysis.isLoading && analysis.isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4">
              <p className="text-sm font-semibold text-destructive">
                {(analysis.error as { response?: { data?: { detail?: string } } })?.response?.data
                  ?.detail ?? "Unable to compute spectrum and statistics."}
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() => void analysis.refetch()}
              >
                Retry
              </Button>
            </div>
          )}

          {analysis.data && <FftSpectrumPanel analysis={analysis.data} />}

          {/* ── Vibration Parameters ───────────────────────────────────── */}
          {analysis.data && (
            <section className="rounded-xl border border-border bg-white p-g3">
              <header className="mb-g3">
                <h3 className="text-sm font-bold text-brand">Vibration Parameters</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Computed over the whole capture ({analysis.data.sample_count.toLocaleString()}{" "}
                  samples), not the visible waveform window. Amplitudes are in the stored
                  engineering unit.
                </p>
              </header>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                <MetricTile label="RMS" value={analysis.data.statistics.rms} />
                <MetricTile label="Peak" value={analysis.data.statistics.peak} />
                <MetricTile label="Peak-to-Peak" value={analysis.data.statistics.peak_to_peak} />
                <MetricTile
                  label="Crest Factor"
                  value={analysis.data.statistics.crest_factor}
                  hint="Peak ÷ RMS"
                />
                <MetricTile
                  label="Kurtosis"
                  value={analysis.data.statistics.kurtosis}
                  hint="Excess — Gaussian = 0"
                />
                <MetricTile label="Skewness" value={analysis.data.statistics.skewness} />
              </div>
              <p className="mt-g3 text-xs text-muted-foreground leading-relaxed">
                <strong>Dominant frequency</strong>{" "}
                {analysis.data.spectrum.dominant_frequency_hz.toFixed(2)} Hz at{" "}
                {formatMetric(analysis.data.spectrum.dominant_amplitude)} — the largest spectral
                line above DC. It is a measured spectral peak, not an identified fault or a shaft
                speed.
              </p>
            </section>
          )}

          {!samples.isLoading && !samples.isError && data && data.samples.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No samples in this window. Try a smaller offset.
            </p>
          )}
        </>
      )}
    </div>
  );
}

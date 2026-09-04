import React, { useCallback, useEffect, useState } from "react";
import { AlignJustify, Box, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { FFTCascadePlot } from "@/components/analysis/waterfall/FFTCascadePlot";
import { FFTWaterfall3D } from "@/components/analysis/waterfall/FFTWaterfall3D";
import { WaterfallControls } from "@/components/analysis/waterfall/WaterfallControls";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { useWaterfallData } from "@/hooks/useWaterfallData";
import { downloadWaterfallCsv } from "@/lib/waterfall-export";
import { cn } from "@/lib/utils";
import type { WaterfallMode, WaterfallSpectrum } from "@/types/waterfall";

const DEFAULT_COUNT = 40;

export type SpectraView = "waterfall" | "cascade";

const VIEWS: { id: SpectraView; label: string; icon: typeof Box }[] = [
  { id: "waterfall", label: "3D Waterfall", icon: Box },
  { id: "cascade", label: "2D Cascade", icon: AlignJustify },
];

function ViewSwitch({
  value,
  onChange,
  disabled,
}: {
  value: SpectraView;
  onChange: (view: SpectraView) => void;
  disabled?: boolean;
}) {
  return (
    <div
      role="tablist"
      aria-label="Spectra view"
      className="inline-flex rounded-lg border border-border bg-white p-0.5"
    >
      {VIEWS.map((view) => {
        const Icon = view.icon;
        const active = value === view.id;
        return (
          <button
            key={view.id}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(view.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]",
              "disabled:cursor-not-allowed disabled:opacity-50",
              active
                ? "bg-brand text-white"
                : "text-muted-foreground hover:bg-warm hover:text-foreground"
            )}
          >
            <Icon size={14} aria-hidden />
            {view.label}
          </button>
        );
      })}
    </div>
  );
}

/** Keeps the 3D area in the 600–750px band without pinning it to one screen size. */
function useWaterfallHeight(): number {
  const [height, setHeight] = useState(660);

  useEffect(() => {
    const measure = () => {
      const available = window.innerHeight - 300;
      setHeight(Math.round(Math.min(750, Math.max(600, available))));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  return height;
}

function errorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || "Could not load waterfall data. Check the sensor selection and try again.";
}

interface WaterfallTabProps {
  sensorId: string;
  channelCount: number;
  defaultChannel?: number;
  /**
   * Controlled 3D/2D view. Both renderings read the same waterfall query, so
   * when an outer selector already lists "3D Waterfall" and "2D Cascade" as
   * separate entries, it drives this instead — and the internal switch, which
   * would then be a second control for the same choice, is hidden.
   *
   * Left undefined the tab stays self-contained and shows its own switch.
   */
  view?: SpectraView;
}

export function WaterfallTab({
  sensorId,
  channelCount,
  defaultChannel = 0,
  view: viewProp,
}: WaterfallTabProps) {
  const [internalView, setInternalView] = useState<SpectraView>("waterfall");
  const view = viewProp ?? internalView;
  const [mode, setMode] = useState<WaterfallMode>("last");
  const [count, setCount] = useState(DEFAULT_COUNT);
  const [spectrum, setSpectrum] = useState<WaterfallSpectrum>("fft_spectrum");
  const [channel, setChannel] = useState(defaultChannel);
  const [seed, setSeed] = useState(1);

  const height = useWaterfallHeight();
  const enabled = !!sensorId;

  useEffect(() => {
    if (channel >= channelCount) setChannel(Math.max(0, channelCount - 1));
  }, [channel, channelCount]);

  const { data, model, isLoading, isFetching, isError, error, refetch, hasCaptures } =
    useWaterfallData({
      sensorId,
      channel,
      count,
      mode,
      plotType: spectrum,
      seed,
      enabled,
    });

  const handleReshuffle = useCallback(() => setSeed((s) => s + 1), []);

  const handleCsv = useCallback(() => {
    if (model && data) downloadWaterfallCsv(model, data);
  }, [model, data]);

  return (
    <div className={analysisBodyStack}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <AnalysisSectionHeader
          icon={view === "waterfall" ? Box : AlignJustify}
          title={view === "waterfall" ? "3D FFT Waterfall" : "2D FFT Cascade"}
          subtitle={
            view === "waterfall"
              ? "Stacked spectra across captures — frequency across, amplitude up, capture into the scene."
              : "The same captures stacked in 2D — each trace offset vertically to compare spectra over time."
          }
          className="mb-0 pb-0 border-b-0"
        />
        {viewProp === undefined && (
          <ViewSwitch value={view} onChange={setInternalView} disabled={!enabled} />
        )}
      </div>

      {!enabled && (
        <p className="text-sm text-muted-foreground">
          Select an equipment and sensor above to build the waterfall.
        </p>
      )}

      {enabled && (
        <>
          <WaterfallControls
            mode={mode}
            onModeChange={setMode}
            count={count}
            onCountChange={setCount}
            spectrum={spectrum}
            onSpectrumChange={setSpectrum}
            channel={channel}
            channelCount={channelCount}
            onChannelChange={setChannel}
            onReshuffle={handleReshuffle}
            totalAvailable={data?.total_available ?? 0}
            disabled={isLoading}
          />

          {isLoading && (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-8 justify-center">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">
                Loading {view === "cascade" ? "cascade" : "waterfall"} data…
              </p>
            </div>
          )}

          {!isLoading && isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4">
              <p className="text-sm font-semibold text-destructive">{errorDetail(error)}</p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={refetch}
              >
                Retry
              </Button>
            </div>
          )}

          {!isLoading && !isError && !hasCaptures && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-10 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-brand/5 text-brand">
                <Box size={24} aria-hidden />
              </div>
              <h3 className="mt-4 text-base font-bold text-foreground">
                No FFT captures available
              </h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
                {data && data.total_available > 0
                  ? `This sensor has ${data.total_available} capture(s), but none produced a usable spectrum on ch${channel}. Try another channel.`
                  : "Upload sensor data for this sensor — every parsed capture becomes one trace."}
              </p>
            </div>
          )}

          {!isLoading && !isError && hasCaptures && model && data && (
            <>
              {view === "waterfall" ? (
                <FFTWaterfall3D
                  model={model}
                  meta={data}
                  height={height}
                  onRefresh={refetch}
                  isRefreshing={isFetching}
                />
              ) : (
                <FFTCascadePlot
                  model={model}
                  meta={data}
                  height={height}
                  onRefresh={refetch}
                  isRefreshing={isFetching}
                />
              )}
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={<Download size={14} />}
                  onClick={handleCsv}
                >
                  Export data (CSV)
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Compass, Loader2 } from "lucide-react";
import { listUploads } from "@/api/measurements";
import { Button } from "@/components/ui/Button";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { PolarVectorPlot } from "@/components/analysis/vector/PolarVectorPlot";
import { VectorControls } from "@/components/analysis/vector/VectorControls";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { useVibrationVector } from "@/hooks/useVibrationVector";

/** Interpretation aids only — diagnosis stays with the rule-book/diagnosis system. */
const PATTERNS: { shape: string; meaning: string }[] = [
  { shape: "Tight cluster", meaning: "Amplitude and phase both stable." },
  { shape: "Long radial vector", meaning: "Higher amplitude with relatively stable phase." },
  { shape: "Arc", meaning: "Phase changes while amplitude stays relatively stable." },
  { shape: "Spiral", meaning: "Amplitude and phase change together." },
  {
    shape: "Loop with ~180° sweep and an amplitude peak",
    meaning: "Review the speed/frequency relationship for critical-speed behaviour.",
  },
];

function useVectorHeight(): number {
  const [height, setHeight] = useState(640);
  useEffect(() => {
    const measure = () =>
      setHeight(Math.round(Math.min(700, Math.max(600, window.innerHeight - 300))));
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  return height;
}

function errorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || "Unable to calculate vibration vector.";
}

interface VectorTabProps {
  selectedUploadId: string;
  sensorId: string;
  channelCount: number;
  defaultChannel?: number;
}

export function VectorTab({
  selectedUploadId,
  sensorId,
  channelCount,
  defaultChannel = 0,
}: VectorTabProps) {
  const [channel, setChannel] = useState(defaultChannel);
  const [targetHz, setTargetHz] = useState("");
  const [blockSize, setBlockSize] = useState<number | "">("");

  const height = useVectorHeight();

  // The waterfall works from a sensor alone, so requiring a timeline click here would
  // make this tab look broken. Fall back to the newest parsed capture. Same query key
  // as the page, so React Query serves it from cache rather than refetching.
  const uploadsQuery = useQuery({
    queryKey: ["sensor-uploads", sensorId],
    queryFn: async () => (await listUploads(sensorId)).items,
    enabled: !selectedUploadId && !!sensorId,
  });

  const fallbackUploadId = useMemo(() => {
    const parsed = (uploadsQuery.data ?? []).filter((u) => u.parse_status === "parsed");
    return parsed.length ? parsed[0].id : ""; // listUploads returns newest first
  }, [uploadsQuery.data]);

  const effectiveUploadId = selectedUploadId || fallbackUploadId;
  const usingFallback = !selectedUploadId && !!fallbackUploadId;
  const enabled = !!effectiveUploadId;

  useEffect(() => {
    if (channel >= channelCount) setChannel(Math.max(0, channelCount - 1));
  }, [channel, channelCount]);

  const parsedTarget = useMemo(() => {
    const value = Number(targetHz);
    return targetHz !== "" && Number.isFinite(value) && value > 0 ? value : undefined;
  }, [targetHz]);

  const { data, model, isLoading, isFetching, isError, error, refetch, hasBlocks } =
    useVibrationVector({
      uploadId: effectiveUploadId,
      channel,
      targetHz: parsedTarget,
      blockSize: blockSize === "" ? undefined : blockSize,
      enabled,
    });

  return (
    <div className={analysisBodyStack}>
      <AnalysisSectionHeader
        icon={Compass}
        title="Polar / Vibration Vector"
        subtitle="Amplitude and self-referenced phase at one frequency, block by block within the selected capture."
        className="mb-0 pb-0 border-b-0"
      />

      {!enabled && uploadsQuery.isLoading && (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
          <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
          <p className="text-sm text-muted-foreground">Loading vibration vector…</p>
        </div>
      )}

      {!enabled && !uploadsQuery.isLoading && (
        <p className="text-sm text-muted-foreground">
          {sensorId
            ? "No parsed captures for this sensor yet. Upload sensor data, then select a capture on the timeline."
            : "Select an equipment and sensor above to display the vibration vector."}
        </p>
      )}

      {enabled && (
        <>
          {usingFallback && (
            <p className="text-xs text-muted-foreground">
              Showing the most recent capture — pick a different one on the timeline to change it.
            </p>
          )}

          <VectorControls
            channel={channel}
            channelCount={channelCount}
            onChannelChange={setChannel}
            targetHz={targetHz}
            onTargetHzChange={setTargetHz}
            candidates={data?.candidates ?? []}
            blockSize={blockSize}
            onBlockSizeChange={setBlockSize}
            disabled={isLoading}
          />

          {isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">Loading vibration vector…</p>
            </div>
          )}

          {!isLoading && isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4">
              <p className="text-sm font-semibold text-destructive">{errorDetail(error)}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                If no frequency of interest is available, pick one above or enter a target
                frequency directly.
              </p>
              <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={refetch}>
                Retry
              </Button>
            </div>
          )}

          {!isLoading && !isError && hasBlocks && model && data && !model.hasSignificantAmplitude && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-8 text-center">
              <h3 className="text-base font-bold text-foreground">
                No significant vibration amplitude at the selected frequency
              </h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
                Every block reads zero at {data.bin_hz.toFixed(2)} Hz on CH {data.channel + 1}. Try a
                different order of interest, another channel, or a larger block size.
              </p>
            </div>
          )}

          {!isLoading && !isError && !hasBlocks && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-8 text-center">
              <h3 className="text-base font-bold text-foreground">No analysis blocks available</h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
                This capture is too short for the selected block size. Choose a smaller block size.
              </p>
            </div>
          )}

          {!isLoading && !isError && hasBlocks && model && data && model.hasSignificantAmplitude && (
            <>
              <PolarVectorPlot
                model={model}
                meta={data}
                height={height}
                onRefresh={refetch}
                isRefreshing={isFetching}
              />

              <div className="rounded-lg border border-border bg-white p-4">
                <h4 className="text-sm font-bold text-foreground">Reading the pattern</h4>
                <p className="mt-1 text-xs text-muted-foreground">
                  Interpretation aids only — these are not fault diagnoses. Confirm any finding
                  against the diagnosis and rule-book workflow.
                </p>
                <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                  {PATTERNS.map((p) => (
                    <div key={p.shape} className="text-xs">
                      <dt className="font-semibold text-foreground">{p.shape}</dt>
                      <dd className="text-muted-foreground">{p.meaning}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Colour encodes block order only (first → latest), never severity. The first block
                  defines 0° by definition, so only phase changes between blocks are meaningful.
                </p>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

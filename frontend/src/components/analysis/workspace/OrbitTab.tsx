import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleDot, Loader2 } from "lucide-react";
import { listUploads } from "@/api/measurements";
import { Button } from "@/components/ui/Button";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { CasingOrbitPlot } from "@/components/analysis/orbit/CasingOrbitPlot";
import { OrbitControls, type OrthogonalityCheck } from "@/components/analysis/orbit/OrbitControls";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { useCasingOrbit } from "@/hooks/useCasingOrbit";
import { useVibrationSettings } from "@/hooks/useVibrationSettings";

/** Interpretation aids only — never a diagnosis. */
const PATTERNS: { shape: string; meaning: string }[] = [
  { shape: "Near-circular 1×", meaning: "Pattern may be consistent with unbalance-type response." },
  { shape: "Ellipse", meaning: "May reflect anisotropic support stiffness or a directional response." },
  { shape: "Figure-eight / inner loop", meaning: "Strong harmonic interaction; review alignment and coupling alongside other evidence." },
  { shape: "Flattened or clipped", meaning: "May be consistent with rub, contact or preload." },
  { shape: "Erratic / non-repeatable", meaning: "May indicate looseness, noise or an unstable response." },
];

function useOrbitHeight(): number {
  const [height, setHeight] = useState(640);
  useEffect(() => {
    const measure = () =>
      setHeight(Math.round(Math.min(700, Math.max(560, window.innerHeight - 320))));
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  return height;
}

/**
 * Orthogonality comes from the existing Vibration Settings channel map (axis per
 * channel). An orbit needs two RADIAL directions, so vertical + horizontal is the valid
 * pair; axial is out of the radial plane. That configuration is stored locally by the
 * Settings page, so it is advisory rather than authoritative.
 */
function useOrthogonality(xChannel: number, yChannel: number): OrthogonalityCheck {
  const { saved } = useVibrationSettings();
  return useMemo(() => {
    const find = (ch: number) => saved.channels.find((c) => c.channelNo === ch + 1);
    const xAxis = find(xChannel)?.axis || null;
    const yAxis = find(yChannel)?.axis || null;

    if (!xAxis || !yAxis) {
      return {
        isOrthogonal: null,
        xAxis,
        yAxis,
        message: "Channel axes not configured — orthogonality unverified",
      };
    }
    const radial = new Set(["vertical", "horizontal"]);
    if (radial.has(xAxis) && radial.has(yAxis) && xAxis !== yAxis) {
      return {
        isOrthogonal: true,
        xAxis,
        yAxis,
        message: `Orthogonal pair detected (${xAxis} × ${yAxis})`,
      };
    }
    return {
      isOrthogonal: false,
      xAxis,
      yAxis,
      message: `Not a radial orthogonal pair (${xAxis} × ${yAxis})`,
    };
  }, [saved.channels, xChannel, yChannel]);
}

function errorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || "Unable to calculate the casing orbit.";
}

interface OrbitTabProps {
  selectedUploadId: string;
  sensorId: string;
  channelCount: number;
}

export function OrbitTab({ selectedUploadId, sensorId, channelCount }: OrbitTabProps) {
  const [xChannel, setXChannel] = useState(0);
  const [yChannel, setYChannel] = useState(1);
  const [harmonic, setHarmonic] = useState(1);
  const [bandwidthPercent, setBandwidthPercent] = useState(20);
  const [filterRevolutions, setFilterRevolutions] = useState<number | "auto">("auto");
  const [displayRevolutions, setDisplayRevolutions] = useState(1);
  const [showUnfiltered, setShowUnfiltered] = useState(false);

  const height = useOrbitHeight();
  const orthogonality = useOrthogonality(xChannel, yChannel);

  // Same fallback as the vector tab: usable straight after picking a sensor.
  const uploadsQuery = useQuery({
    queryKey: ["sensor-uploads", sensorId],
    queryFn: async () => (await listUploads(sensorId)).items,
    enabled: !selectedUploadId && !!sensorId,
  });
  const fallbackUploadId = useMemo(() => {
    const parsed = (uploadsQuery.data ?? []).filter((u) => u.parse_status === "parsed");
    return parsed.length ? parsed[0].id : "";
  }, [uploadsQuery.data]);
  const effectiveUploadId = selectedUploadId || fallbackUploadId;

  useEffect(() => {
    if (yChannel >= channelCount) setYChannel(Math.max(0, channelCount - 1));
    if (xChannel >= channelCount) setXChannel(0);
  }, [xChannel, yChannel, channelCount]);

  const { data, isLoading, isFetching, isError, error, refetch, hasSignal } = useCasingOrbit({
    uploadId: effectiveUploadId,
    xChannel,
    yChannel,
    harmonic,
    bandwidthPercent,
    filterRevolutions: filterRevolutions === "auto" ? undefined : filterRevolutions,
    displayRevolutions,
    includeUnfiltered: showUnfiltered,
    enabled: !!effectiveUploadId,
  });

  const enabled = !!effectiveUploadId;

  return (
    <div className={analysisBodyStack}>
      <AnalysisSectionHeader
        icon={CircleDot}
        title="Casing Orbit / Lissajous"
        subtitle="X(t) against Y(t) from two synchronously-sampled accelerometer channels — casing motion, not shaft centreline."
        className="mb-0 pb-0 border-b-0"
      />

      {!enabled && !uploadsQuery.isLoading && (
        <p className="text-sm text-muted-foreground">
          {sensorId
            ? "No parsed captures for this sensor yet. Upload sensor data to plot an orbit."
            : "Select an equipment and sensor above to plot the casing orbit."}
        </p>
      )}

      {channelCount < 2 && enabled && (
        <p className="text-sm text-signal-dark">
          An orbit needs two channels; this capture has only one.
        </p>
      )}

      {enabled && channelCount >= 2 && (
        <>
          <OrbitControls
            xChannel={xChannel}
            yChannel={yChannel}
            channelCount={channelCount}
            onXChannelChange={setXChannel}
            onYChannelChange={setYChannel}
            harmonic={harmonic}
            onHarmonicChange={setHarmonic}
            bandwidthPercent={bandwidthPercent}
            onBandwidthChange={setBandwidthPercent}
            filterRevolutions={filterRevolutions}
            onFilterRevolutionsChange={setFilterRevolutions}
            displayRevolutions={displayRevolutions}
            onDisplayRevolutionsChange={setDisplayRevolutions}
            showUnfiltered={showUnfiltered}
            onShowUnfilteredChange={setShowUnfiltered}
            orthogonality={orthogonality}
            disabled={isLoading}
          />

          {isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">Loading casing orbit…</p>
            </div>
          )}

          {!isLoading && isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4">
              <p className="text-sm font-semibold text-destructive">{errorDetail(error)}</p>
              <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={refetch}>
                Retry
              </Button>
            </div>
          )}

          {!isLoading && !isError && data && !hasSignal && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-8 text-center">
              <h3 className="text-base font-bold text-foreground">
                No significant synchronous vibration in the selected band
              </h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
                Displacement at {data.centre_hz.toFixed(1)} Hz is below the reliable display range
                on ch{data.x_channel}/ch{data.y_channel}. Try the other harmonic, a wider bandwidth,
                or different channels.
              </p>
            </div>
          )}

          {!isLoading && !isError && data && hasSignal && (
            <>
              {data.warnings.length > 0 && (
                <div className="rounded-lg border border-signal-light/40 bg-signal-light/5 px-4 py-3">
                  <ul className="space-y-1">
                    {data.warnings.map((w) => (
                      <li key={w} className="text-xs text-signal-dark">
                        {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <CasingOrbitPlot
                data={data}
                height={height}
                showUnfiltered={showUnfiltered}
                onRefresh={refetch}
                isRefreshing={isFetching}
              />

              <div className="rounded-lg border border-border bg-white p-4">
                <h4 className="text-sm font-bold text-foreground">Reading the orbit</h4>
                <p className="mt-1 text-xs text-muted-foreground">
                  Interpretation aids only — not fault diagnoses. Correlate with the spectrum, time
                  waveform, speed and machine configuration before drawing a conclusion.
                </p>
                <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                  {PATTERNS.map((p) => (
                    <div key={p.shape} className="text-xs">
                      <dt className="font-semibold text-foreground">{p.shape}</dt>
                      <dd className="text-muted-foreground">{p.meaning}</dd>
                    </div>
                  ))}
                </dl>
                {harmonic === 2 && (
                  <p className="mt-3 text-[11px] text-muted-foreground">
                    2× synchronous component — often useful when investigating alignment or
                    coupling-related harmonic response, but 2× alone does not establish
                    misalignment.
                  </p>
                )}
                {!data.mounting_angle_configured && (
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Probe mounting angle is not configured, so channels are plotted as measured
                    without rotation into a true Cartesian frame.
                  </p>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { Move3D, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField } from "@/components/ui/FormField";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { OneXMigrationPlot } from "@/components/analysis/migration/OneXMigrationPlot";
import { analysisBodyStack, analysisSelectClass } from "@/components/analysis/analysis-layout";
import { useOneXMigration } from "@/hooks/useOneXMigration";
import { MIGRATION_COUNTS } from "@/types/migration";
import { WATERFALL_MODE_LABELS, WATERFALL_MODES } from "@/types/waterfall";

/** Interpretation aids only — never a fault verdict. */
const PATTERNS: { shape: string; meaning: string }[] = [
  { shape: "Straight path through the origin", meaning: "V/H response stays approximately proportional." },
  { shape: "Changing slope", meaning: "The directional response relationship is changing." },
  { shape: "Curved or kinked path", meaning: "Possible change in operating condition, stiffness, loading or resonance response — correlate with speed and spectrum." },
  { shape: "Scattered points", meaning: "Check signal quality, speed tracking, sensor mounting and machine stability." },
];

function useMigrationHeight(): number {
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

function errorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "Unable to calculate the 1× response.";
}

interface MigrationTabProps {
  sensorId: string;
  channelCount: number;
}

export function MigrationTab({ sensorId, channelCount }: MigrationTabProps) {
  const [xChannel, setXChannel] = useState(0);
  const [yChannel, setYChannel] = useState(1);
  const [count, setCount] = useState(40);
  const [mode, setMode] = useState<string>("last");

  const height = useMigrationHeight();
  const enabled = !!sensorId && channelCount >= 2;

  useEffect(() => {
    if (yChannel >= channelCount) setYChannel(Math.max(0, channelCount - 1));
    if (xChannel >= channelCount) setXChannel(0);
  }, [xChannel, yChannel, channelCount]);

  const { data, isLoading, isFetching, isError, error, refetch, hasMigration } =
    useOneXMigration({ sensorId, xChannel, yChannel, count, mode, enabled });

  const channels = Array.from({ length: Math.max(2, channelCount) }, (_, i) => i);

  return (
    <div className={analysisBodyStack}>
      <AnalysisSectionHeader
        icon={Move3D}
        title="1× Amplitude Migration"
        subtitle="Vertical vs Horizontal 1× casing vibration response — one point per capture, tracked at each capture's own shaft frequency."
        className="mb-0 pb-0 border-b-0"
      />

      {!sensorId && (
        <p className="text-sm text-muted-foreground">
          Select an equipment and sensor above to trend the 1× response.
        </p>
      )}

      {sensorId && channelCount < 2 && (
        <p className="text-sm text-signal-dark">
          Two channels are required; this sensor's captures have only one.
        </p>
      )}

      {enabled && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <FormField label="Vertical channel (X)" compact>
              <select
                className={analysisSelectClass}
                value={xChannel}
                onChange={(e) => setXChannel(Number(e.target.value))}
                disabled={isLoading}
              >
                {channels.map((c) => (
                  <option key={c} value={c} disabled={c === yChannel}>
                    CH {c + 1} (ch{c})
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Horizontal channel (Y)" compact>
              <select
                className={analysisSelectClass}
                value={yChannel}
                onChange={(e) => setYChannel(Number(e.target.value))}
                disabled={isLoading}
              >
                {channels.map((c) => (
                  <option key={c} value={c} disabled={c === xChannel}>
                    CH {c + 1} (ch{c})
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Selection" compact>
              <select
                className={analysisSelectClass}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                disabled={isLoading}
              >
                {WATERFALL_MODES.map((m) => (
                  <option key={m} value={m}>
                    {WATERFALL_MODE_LABELS[m]}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Captures (N)" compact>
              <select
                className={analysisSelectClass}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                disabled={isLoading}
              >
                {MIGRATION_COUNTS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white px-4 py-8">
              <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
              <p className="text-sm text-muted-foreground">Calculating 1× response…</p>
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

          {!isLoading && !isError && data && !hasMigration && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-6 py-8 text-center">
              <h3 className="text-base font-bold text-foreground">
                {data.returned_count === 0
                  ? "No vibration captures available."
                  : "At least two valid captures are required to show migration."}
              </h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
                {data.skipped_count > 0
                  ? `${data.skipped_count} of ${data.returned_count} captures could not produce a reliable 1× response — most often a missing channel or no shaft-frequency estimate.`
                  : "Upload more captures for this sensor, or widen the capture selection."}
              </p>
            </div>
          )}

          {!isLoading && !isError && data && hasMigration && (
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

              <OneXMigrationPlot
                data={data}
                height={height}
                onRefresh={refetch}
                isRefreshing={isFetching}
              />

              <div className="rounded-lg border border-border bg-white p-4">
                <h4 className="text-sm font-bold text-foreground">Reading the migration path</h4>
                <p className="mt-1 text-xs text-muted-foreground">
                  It tracks the 1× vibration amplitude relationship between two casing-mounted
                  accelerometer directions across captures, showing how the directional response
                  changes over time or operating condition. It is <strong>not</strong> a
                  shaft-centreline position measurement — static shaft position requires
                  DC-capable proximity probes.
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
                  These are interpretation aids, not diagnoses. Correlate with the spectrum, time
                  waveform, speed and machine configuration. Relative V-H phase is a cross-channel
                  difference only; absolute shaft phase requires a keyphasor.
                </p>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

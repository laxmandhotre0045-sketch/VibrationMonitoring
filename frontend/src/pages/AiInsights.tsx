import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronDown,
  Gauge,
  Layers,
  ShieldQuestion,
} from "lucide-react";

import { listSensors } from "@/api/sensorExport";
import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBox";
import { cn } from "@/lib/utils";
import {
  useAcknowledgeAlarm,
  useAlarms,
  useCaptureMode,
  useCaptureScores,
  useDetectorScores,
  useScoredCaptures,
  useSensitivity,
} from "@/hooks/useAnomaly";
import {
  BAND_LABELS,
  CONDITION_LABELS,
  CONDITION_ORDER,
  PROFILE_BLURBS,
  PROFILE_LABELS,
  explainHeldBack,
  explainNotEscalating,
  formatConfidence,
  formatDeviation,
  formatDuration,
  formatScore,
  rankAlarms,
  summariseCapture,
  tallyBands,
  toneForBand,
} from "@/lib/anomaly-view";
import type { SensitivityProfile } from "@/types/anomaly";

const PROFILES: SensitivityProfile[] = [
  "conservative",
  "balanced",
  "early_warning",
  "expert",
];

/**
 * AI Insights — what the platform made of each capture, and what is ringing.
 *
 * Two rules shape the page and both are easy to lose in a presentation layer.
 *
 * **A reading nothing could score is shown as "—", never as a zero and never
 * in green.** A machine nobody has learned a normal for must not outrank a
 * monitored healthy one, so the unscored count sits in the headline and an
 * unscored row gets a neutral badge.
 *
 * **Held-back findings are shown, not hidden.** Somebody who thinks the
 * platform is too quiet needs to see what it is sitting on and why.
 *
 * Colours come from the design system's semantic tokens (`text-foreground`,
 * `text-muted-foreground`, `bg-card`) rather than fixed slate values. The
 * first version of this page used dark-theme greys on a light-theme app and
 * most of it was unreadable — the tokens are what make the page follow the
 * theme instead of guessing at it.
 */

/** A labelled select matching the one the hierarchy filter bar uses. */
function Field({
  label,
  value,
  onChange,
  disabled,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative flex-1 rounded-lg border bg-card",
        disabled ? "border-border opacity-60" : "border-border hover:border-signal-light/55",
      )}
    >
      <span className="absolute -top-2 left-2.5 bg-card px-1 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
        className="w-full cursor-pointer appearance-none bg-transparent py-2.5 pl-3 pr-8 text-sm font-semibold text-foreground outline-none disabled:cursor-not-allowed"
      >
        {children}
      </select>
      <ChevronDown
        size={15}
        aria-hidden
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}

export function AiInsightsPage() {
  const [sensorId, setSensorId] = useState<string>("");
  const [uploadId, setUploadId] = useState<string>("");

  const sensorsQuery = useQuery({
    queryKey: ["insights-sensors"],
    queryFn: () => listSensors(""),
    staleTime: 300_000,
  });

  const sensors = useMemo(() => sensorsQuery.data ?? [], [sensorsQuery.data]);
  const sensor = sensors.find((item) => item.sensor_id === sensorId) ?? null;

  useEffect(() => {
    if (!sensorId && sensors.length > 0) setSensorId(sensors[0].sensor_id);
  }, [sensors, sensorId]);

  /**
   * Only captures that have actually been scored can be shown.
   *
   * The uploads list cannot answer which those are. Its `features_status`
   * says "pending" on 157 of this machine's uploads while 120 of them carry
   * scores — the column is written by the ingest path and the scores were
   * also written by backfill scripts that never touched it. Filtering on it
   * hid 116 analysed captures and offered four; defaulting to the newest
   * upload opened the page on one with nothing to show.
   *
   * So the picker is fed by the score table, which is the thing being
   * picked from.
   */
  const { captures, isLoading: capturesLoading } = useScoredCaptures(sensorId);

  useEffect(() => {
    if (captures.length === 0) {
      setUploadId("");
      return;
    }
    if (!captures.some((item) => item.upload_id === uploadId)) {
      setUploadId(captures[0].upload_id);
    }
  }, [captures, uploadId]);

  const { capture, isLoading: scoresLoading } = useCaptureScores(uploadId);
  const { detectors } = useDetectorScores(uploadId);
  const { mode } = useCaptureMode(uploadId);
  const { summary, isLoading: alarmsLoading } = useAlarms(sensorId);
  const { sensitivity, save, isSaving } = useSensitivity(sensor?.equipment_id);
  const acknowledge = useAcknowledgeAlarm(sensorId);

  const bands = capture ? tallyBands(capture.scores) : [];
  const alarms = summary ? rankAlarms(summary.alarms) : [];

  return (
    <div className="space-y-6">
      <PageHero
        vibrationBg
        title="AI Insights"
        subtitle="How unusual each reading was, what is ringing, and what is being held back."
      />

      {/* ---------------------------------------------- what to look at -- */}
      <GlassCard className="p-5">
        <div className="flex flex-col gap-4 sm:flex-row">
          <Field label="Machine" value={sensorId} onChange={setSensorId}>
            {sensors.map((item) => (
              <option key={item.sensor_id} value={item.sensor_id}>
                {item.machine_name} — {item.mounting_location} {item.orientation}
              </option>
            ))}
          </Field>

          <Field
            label={`Capture${captures.length > 0 ? ` (${captures.length} analysed)` : ""}`}
            value={uploadId}
            onChange={setUploadId}
            disabled={captures.length === 0}
          >
            {captures.map((item) => (
              <option key={item.upload_id} value={item.upload_id}>
                {new Date(item.created_at).toLocaleString()}
                {item.worst_score !== null
                  ? ` — worst ${item.worst_score.toFixed(0)}`
                  : ""}
              </option>
            ))}
          </Field>
        </div>

        {!capturesLoading && captures.length === 0 && sensorId && (
          <p className="text-helper mt-3">
            No capture on this machine has been scored yet, so there is
            nothing to show. That is not the same as a clean result &mdash; it
            means nothing has looked.
          </p>
        )}
      </GlassCard>

      {/* ------------------------------------------------ this capture --- */}
      <GlassCard className="p-6">
        <header className="mb-4 flex flex-wrap items-center gap-2">
          <Gauge size={16} className="text-brand" aria-hidden />
          <h2 className="text-card-title text-brand">This capture</h2>
          {mode && (
            <StatusBadge tone={mode.is_unknown ? "neutral" : "healthy"}>
              {mode.is_unknown ? "mode unknown" : mode.label.replace(/_/g, " ")}
            </StatusBadge>
          )}
        </header>

        {scoresLoading && <p className="text-helper">Loading&hellip;</p>}

        {!scoresLoading && !capture && (
          <p className="text-helper">
            Nothing has been scored for this capture.
          </p>
        )}

        {capture && (
          <>
            <p className="mb-4 text-sm text-foreground">
              {summariseCapture(capture)}
            </p>

            <div className="mb-5 flex flex-wrap gap-2">
              {bands.map(({ band, count }) => (
                <StatusBadge key={band} tone={toneForBand(band)}>
                  {BAND_LABELS[band]}: {count}
                </StatusBadge>
              ))}
              {capture.unscored > 0 && (
                // Never green, never a zero. This is the count of readings
                // nothing has ever been compared to.
                <StatusBadge tone="neutral">
                  Not scored: {capture.unscored}
                </StatusBadge>
              )}
            </div>

            {capture.scores.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="text-table-header pb-2 pr-3">Feature</th>
                      <th className="text-table-header pb-2 pr-3">Ch</th>
                      <th className="text-table-header pb-2 pr-3 text-right">
                        Score
                      </th>
                      <th className="text-table-header pb-2 pr-3">Band</th>
                      <th className="text-table-header pb-2 pr-3">Deviation</th>
                      <th className="text-table-header pb-2">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {capture.scores.slice(0, 25).map((score) => (
                      <tr
                        key={`${score.channel}-${score.feature_code}`}
                        className="border-b border-border/60"
                      >
                        <td className="py-2 pr-3 font-medium text-foreground">
                          {score.feature_code}
                        </td>
                        <td className="py-2 pr-3 text-muted-foreground">
                          {score.channel}
                        </td>
                        <td className="py-2 pr-3 text-right font-semibold tabular-nums text-foreground">
                          {formatScore(score)}
                        </td>
                        <td className="py-2 pr-3">
                          <StatusBadge tone={toneForBand(score.band)}>
                            {score.band ? BAND_LABELS[score.band] : "Not scored"}
                          </StatusBadge>
                        </td>
                        <td className="py-2 pr-3 tabular-nums text-muted-foreground">
                          {formatDeviation(score.z_score)}
                        </td>
                        <td className="py-2 tabular-nums text-muted-foreground">
                          {formatConfidence(score.confidence)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {capture.scores.length > 25 && (
                  <p className="text-helper mt-3">
                    Showing the 25 most unusual of {capture.scores.length}.
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </GlassCard>

      {/* ------------------------------------------- joint detectors ----- */}
      {detectors && detectors.length > 0 && (
        <GlassCard className="p-6">
          <header className="mb-2 flex items-center gap-2">
            <Layers size={16} className="text-brand" aria-hidden />
            <h2 className="text-card-title text-brand">
              Looking at the features together
            </h2>
          </header>
          <p className="text-helper mb-4">
            These two judge the whole channel at once, so they can flag a
            combination of readings that no single feature would.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {detectors.slice(0, 6).map((detector) => (
              <div
                key={`${detector.channel}-${detector.method}`}
                className="rounded-lg border border-border p-3"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">
                    Ch {detector.channel} &middot;{" "}
                    {detector.method === "pca_residual"
                      ? "Does not fit the pattern"
                      : "Isolated from history"}
                  </span>
                  <span className="font-semibold tabular-nums text-foreground">
                    {formatScore(detector)}
                  </span>
                </div>
                {detector.drivers.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Mostly{" "}
                    {detector.drivers
                      .slice(0, 2)
                      .map((d) => `${d.feature} (${Math.round(d.share * 100)}%)`)
                      .join(", ")}
                  </p>
                )}
                {!detector.is_scored && detector.reason && (
                  <p className="text-xs text-muted-foreground">
                    {detector.reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* ------------------------------------------------------ alarms --- */}
      <GlassCard className="p-6">
        <header className="mb-4 flex flex-wrap items-center gap-2">
          <AlertTriangle size={16} className="text-machine-warning" aria-hidden />
          <h2 className="text-card-title text-brand">Alarms</h2>
          {summary && (
            <StatusBadge tone={summary.alarming > 0 ? "warning" : "healthy"}>
              {summary.alarming} ringing
            </StatusBadge>
          )}
          {summary && summary.escalating > 0 && (
            // A separate badge, not a bigger number. "Getting worse" is a
            // different claim from "unusual" and folding them together
            // loses the one that decides what happens next.
            <StatusBadge tone="critical">
              {summary.escalating} getting worse
            </StatusBadge>
          )}
        </header>

        {alarmsLoading && <p className="text-helper">Loading&hellip;</p>}

        {summary && alarms.length === 0 && (
          <p className="text-sm text-foreground">
            Nothing is ringing on this machine.
          </p>
        )}

        {alarms.map((alarm) => (
          <div
            key={`${alarm.channel}-${alarm.feature_code}`}
            className="mb-3 rounded-lg border border-machine-warning/30 bg-machine-warning/5 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <span className="font-semibold text-foreground">
                  {alarm.feature_code}
                </span>
                <span className="ml-2 text-sm text-muted-foreground">
                  channel {alarm.channel} &middot; {formatScore(alarm)} &middot;{" "}
                  {alarm.run_length} of {alarm.required} captures
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {formatDuration(alarm.first_alarmed_at)}
                </span>
                {alarm.acknowledged_at ? (
                  <StatusBadge tone="neutral">
                    Seen by {alarm.acknowledged_by ?? "someone"}
                  </StatusBadge>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      acknowledge.mutate({
                        channel: alarm.channel,
                        featureCode: alarm.feature_code,
                      })
                    }
                    disabled={acknowledge.isPending}
                    className="btn-cta-outline px-3 py-1 text-xs"
                  >
                    Acknowledge
                  </button>
                )}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {CONDITION_ORDER.map((key) => (
                <span
                  key={key}
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[11px] font-medium",
                    alarm.conditions[key]
                      ? "bg-machine-healthy/10 text-machine-healthy"
                      : "bg-muted text-muted-foreground line-through",
                  )}
                  title={
                    alarm.conditions[key]
                      ? `${CONDITION_LABELS[key]}: met`
                      : `${CONDITION_LABELS[key]}: not met`
                  }
                >
                  {CONDITION_LABELS[key]}
                </span>
              ))}
            </div>

            {alarm.escalating ? (
              <p className="mt-2 text-sm font-medium text-machine-critical">
                Getting worse &mdash; climbing, on a machine whose speed held
                steady.
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                {explainNotEscalating(alarm)}
              </p>
            )}

            {alarm.reason && (
              <p className="mt-2 text-sm text-muted-foreground">
                {alarm.reason}
              </p>
            )}
          </div>
        ))}

        {summary && summary.suppressed.length > 0 && (
          <div className="mt-5 border-t border-border pt-4">
            <header className="mb-2 flex items-center gap-2">
              <ShieldQuestion size={15} className="text-muted-foreground" aria-hidden />
              <h3 className="text-sm font-semibold text-foreground">
                Past the line, not ringing ({summary.held_back})
              </h3>
            </header>
            <p className="text-helper mb-3">
              Shown rather than hidden: if this machine feels too quiet, this is
              what it is sitting on and why.
            </p>
            <ul className="space-y-2">
              {summary.suppressed.slice(0, 10).map((item) => (
                <li
                  key={`${item.channel}-${item.feature_code}`}
                  className="text-sm text-muted-foreground"
                >
                  <span className="font-medium text-foreground">
                    {item.feature_code}
                  </span>{" "}
                  ch {item.channel} &middot; {formatScore(item)} &mdash;{" "}
                  {explainHeldBack(item)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </GlassCard>

      {/* ------------------------------------------------ sensitivity ---- */}
      {sensitivity && (
        <GlassCard className="p-6">
          <header className="mb-2 flex items-center gap-2">
            <Gauge size={16} className="text-brand" aria-hidden />
            <h2 className="text-card-title text-brand">
              How readily this machine alarms
            </h2>
          </header>
          <p className="text-helper mb-4">
            Currently {sensitivity.score_threshold.toFixed(0)} or above, for{" "}
            {sensitivity.persistence} captures in a row, with at least{" "}
            {formatConfidence(sensitivity.min_confidence)} confidence in the
            baseline behind it.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {PROFILES.map((profile) => {
              const active = sensitivity.profile === profile;
              return (
                <button
                  key={profile}
                  type="button"
                  onClick={() => save({ profile })}
                  disabled={isSaving || active}
                  className={cn(
                    "rounded-lg border p-3 text-left transition",
                    active
                      ? "border-signal-light bg-signal-light/10"
                      : "border-border hover:border-signal-light/55",
                  )}
                >
                  <span className="block text-sm font-semibold text-foreground">
                    {PROFILE_LABELS[profile]}
                    {active && " · in use"}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {PROFILE_BLURBS[profile]}
                  </span>
                </button>
              );
            })}
          </div>

          {sensitivity.updated_by && (
            <p className="text-helper mt-3">
              Last changed by {sensitivity.updated_by}.
            </p>
          )}
        </GlassCard>
      )}
    </div>
  );
}

export default AiInsightsPage;

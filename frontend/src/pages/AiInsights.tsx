import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Gauge, Layers, ShieldQuestion } from "lucide-react";

import { listSensors } from "@/api/sensorExport";
import { listUploads } from "@/api/measurements";
import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBox";
import {
  useAcknowledgeAlarm,
  useAlarms,
  useCaptureMode,
  useCaptureScores,
  useDetectorScores,
  useSensitivity,
} from "@/hooks/useAnomaly";
import {
  BAND_LABELS,
  PROFILE_BLURBS,
  PROFILE_LABELS,
  explainHeldBack,
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
 * Phase 2 scores every reading against a normal learned for that machine in
 * that operating mode, runs two detectors over the whole feature vector at
 * once, and decides which of those scores deserve to become an alarm. All of
 * that was in the database and none of it was on screen.
 *
 * The page is built around one rule that is easy to lose and expensive to
 * lose: **a reading nothing could be scored against is shown as "—", never as
 * a zero and never in green.** A machine nobody has learned a normal for must
 * not outrank a monitored healthy one, and the unscored count sits in the
 * headline rather than being quietly dropped.
 *
 * The second rule is that held-back findings are shown, not hidden. Somebody
 * who thinks the platform is too quiet needs to see what it is sitting on and
 * why — whether it is waiting for the finding to persist, or distrusting the
 * baseline behind it. Those have different fixes.
 */
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

  const uploadsQuery = useQuery({
    queryKey: ["insights-uploads", sensorId],
    queryFn: () => listUploads(sensorId, { pageSize: 50 }),
    enabled: Boolean(sensorId),
    staleTime: 60_000,
  });

  const uploads = uploadsQuery.data?.items ?? [];

  // Newest capture by default: it is the one somebody opening this page is
  // asking about.
  useEffect(() => {
    if (uploads.length > 0) {
      const stillThere = uploads.some((u) => u.id === uploadId);
      if (!stillThere) setUploadId(uploads[0].id);
    } else {
      setUploadId("");
    }
  }, [uploads, uploadId]);

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
      <GlassCard className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm">
            <span className="mb-1 block text-slate-400">Machine</span>
            <select
              id="insights-sensor"
              value={sensorId}
              onChange={(event) => setSensorId(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-slate-100"
            >
              {sensors.map((item) => (
                <option key={item.sensor_id} value={item.sensor_id}>
                  {item.machine_name} — {item.mounting_location} {item.orientation}
                </option>
              ))}
            </select>
          </label>

          <label className="flex-1 text-sm">
            <span className="mb-1 block text-slate-400">Capture</span>
            <select
              id="insights-capture"
              value={uploadId}
              onChange={(event) => setUploadId(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-slate-100"
              disabled={uploads.length === 0}
            >
              {uploads.map((item) => (
                <option key={item.id} value={item.id}>
                  {new Date(item.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        </div>
      </GlassCard>

      {/* ------------------------------------------------ this capture --- */}
      <GlassCard className="p-5">
        <header className="mb-4 flex items-center gap-2">
          <Gauge className="h-5 w-5 text-sky-400" aria-hidden />
          <h2 className="text-lg font-semibold text-slate-100">This capture</h2>
          {mode && (
            <StatusBadge tone={mode.is_unknown ? "neutral" : "healthy"}>
              {mode.is_unknown ? "mode unknown" : mode.label.replace(/_/g, " ")}
            </StatusBadge>
          )}
        </header>

        {scoresLoading && <p className="text-slate-400">Loading…</p>}

        {!scoresLoading && !capture && (
          <p className="text-slate-400">
            Nothing has been scored for this capture yet.
          </p>
        )}

        {capture && (
          <>
            <p className="mb-4 text-slate-200">{summariseCapture(capture)}</p>

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

            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="text-left text-slate-400">
                  <tr>
                    <th className="pb-2 pr-3 font-medium">Feature</th>
                    <th className="pb-2 pr-3 font-medium">Ch</th>
                    <th className="pb-2 pr-3 text-right font-medium">Score</th>
                    <th className="pb-2 pr-3 font-medium">Band</th>
                    <th className="pb-2 pr-3 font-medium">Deviation</th>
                    <th className="pb-2 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {capture.scores.slice(0, 25).map((score) => (
                    <tr
                      key={`${score.channel}-${score.feature_code}`}
                      className="border-t border-white/5"
                    >
                      <td className="py-2 pr-3 text-slate-200">
                        {score.feature_code}
                      </td>
                      <td className="py-2 pr-3 text-slate-400">{score.channel}</td>
                      <td className="py-2 pr-3 text-right tabular-nums text-slate-100">
                        {formatScore(score)}
                      </td>
                      <td className="py-2 pr-3">
                        <StatusBadge tone={toneForBand(score.band)}>
                          {score.band ? BAND_LABELS[score.band] : "Not scored"}
                        </StatusBadge>
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-slate-400">
                        {formatDeviation(score.z_score)}
                      </td>
                      <td className="py-2 tabular-nums text-slate-400">
                        {formatConfidence(score.confidence)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </GlassCard>

      {/* ------------------------------------------- joint detectors ----- */}
      {detectors && detectors.length > 0 && (
        <GlassCard className="p-5">
          <header className="mb-2 flex items-center gap-2">
            <Layers className="h-5 w-5 text-violet-400" aria-hidden />
            <h2 className="text-lg font-semibold text-slate-100">
              Looking at the features together
            </h2>
          </header>
          <p className="mb-4 text-sm text-slate-400">
            These two judge the whole channel at once, so they can flag a
            combination of readings that no single feature would.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {detectors.slice(0, 6).map((detector) => (
              <div
                key={`${detector.channel}-${detector.method}`}
                className="rounded-lg border border-white/10 bg-slate-900/40 p-3"
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm text-slate-300">
                    Ch {detector.channel} ·{" "}
                    {detector.method === "pca_residual"
                      ? "Does not fit the pattern"
                      : "Isolated from history"}
                  </span>
                  <span className="tabular-nums text-slate-100">
                    {formatScore(detector)}
                  </span>
                </div>
                {detector.drivers.length > 0 && (
                  <p className="text-xs text-slate-400">
                    Mostly{" "}
                    {detector.drivers
                      .slice(0, 2)
                      .map((d) => `${d.feature} (${Math.round(d.share * 100)}%)`)
                      .join(", ")}
                  </p>
                )}
                {!detector.is_scored && detector.reason && (
                  <p className="text-xs text-slate-500">{detector.reason}</p>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* ------------------------------------------------------ alarms --- */}
      <GlassCard className="p-5">
        <header className="mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-amber-400" aria-hidden />
          <h2 className="text-lg font-semibold text-slate-100">Alarms</h2>
          {summary && (
            <StatusBadge tone={summary.alarming > 0 ? "warning" : "healthy"}>
              {summary.alarming} ringing
            </StatusBadge>
          )}
        </header>

        {alarmsLoading && <p className="text-slate-400">Loading…</p>}

        {summary && alarms.length === 0 && (
          <p className="text-slate-300">
            Nothing is ringing on this machine.
          </p>
        )}

        {alarms.map((alarm) => (
          <div
            key={`${alarm.channel}-${alarm.feature_code}`}
            className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-medium text-slate-100">
                  {alarm.feature_code}
                </span>
                <span className="ml-2 text-sm text-slate-400">
                  channel {alarm.channel} · {formatScore(alarm)} ·{" "}
                  {alarm.run_length} of {alarm.required} captures
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">
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
                    className="rounded-md border border-white/15 px-2 py-1 text-xs text-slate-200 hover:bg-white/5"
                  >
                    Acknowledge
                  </button>
                )}
              </div>
            </div>
            {alarm.reason && (
              <p className="mt-2 text-sm text-slate-400">{alarm.reason}</p>
            )}
          </div>
        ))}

        {summary && summary.suppressed.length > 0 && (
          <div className="mt-5 border-t border-white/10 pt-4">
            <header className="mb-2 flex items-center gap-2">
              <ShieldQuestion className="h-4 w-4 text-slate-400" aria-hidden />
              <h3 className="text-sm font-medium text-slate-300">
                Past the line, not ringing ({summary.held_back})
              </h3>
            </header>
            <p className="mb-3 text-xs text-slate-500">
              Shown rather than hidden: if this machine feels too quiet, this is
              what it is sitting on and why.
            </p>
            <ul className="space-y-2">
              {summary.suppressed.slice(0, 10).map((item) => (
                <li
                  key={`${item.channel}-${item.feature_code}`}
                  className="text-sm text-slate-400"
                >
                  <span className="text-slate-200">{item.feature_code}</span>{" "}
                  ch {item.channel} · {formatScore(item)} —{" "}
                  {explainHeldBack(item)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </GlassCard>

      {/* ------------------------------------------------ sensitivity ---- */}
      {sensitivity && (
        <GlassCard className="p-5">
          <header className="mb-2 flex items-center gap-2">
            <Gauge className="h-5 w-5 text-emerald-400" aria-hidden />
            <h2 className="text-lg font-semibold text-slate-100">
              How readily this machine alarms
            </h2>
          </header>
          <p className="mb-4 text-sm text-slate-400">
            Currently {sensitivity.score_threshold.toFixed(0)} or above, for{" "}
            {sensitivity.persistence} captures in a row, with at least{" "}
            {formatConfidence(sensitivity.min_confidence)} confidence in the
            baseline behind it.
          </p>

          <div className="grid gap-2 sm:grid-cols-2">
            {PROFILES.map((profile) => {
              const active = sensitivity.profile === profile;
              return (
                <button
                  key={profile}
                  type="button"
                  onClick={() => save({ profile })}
                  disabled={isSaving || active}
                  className={`rounded-lg border p-3 text-left transition ${
                    active
                      ? "border-emerald-400/40 bg-emerald-400/10"
                      : "border-white/10 hover:bg-white/5"
                  }`}
                >
                  <span className="block font-medium text-slate-100">
                    {PROFILE_LABELS[profile]}
                    {active && " · in use"}
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    {PROFILE_BLURBS[profile]}
                  </span>
                </button>
              );
            })}
          </div>

          {sensitivity.updated_by && (
            <p className="mt-3 text-xs text-slate-500">
              Last changed by {sensitivity.updated_by}.
            </p>
          )}
        </GlassCard>
      )}
    </div>
  );
}

export default AiInsightsPage;

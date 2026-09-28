import type { StatusTone } from "@/lib/status-box";
import type {
  Alarm,
  AlarmConditions,
  AnomalyBand,
  CaptureScores,
  FeatureScore,
  HeldBackAlarm,
  SensitivityProfile,
} from "@/types/anomaly";

/**
 * Turning Phase 2's numbers into something readable, without losing what they
 * mean.
 *
 * This file exists so the decisions are testable. A component can be looked
 * at; it cannot be asserted about, and the decisions here are the ones most
 * worth pinning down — chiefly that **a feature nothing could score must
 * never be rendered as a zero or a green tick**. That is the distinction the
 * whole platform is built on, and a presentation layer is the easiest place
 * to throw it away by accident: `score ?? 0` is one keystroke.
 */

export const BAND_LABELS: Record<AnomalyBand, string> = {
  normal: "Normal",
  slight: "Slight deviation",
  watch: "Watch",
  abnormal: "Abnormal",
  high: "High priority",
  critical: "Critical",
};

/** Worst first, which is the order a screen should show them in. */
export const BAND_ORDER: AnomalyBand[] = [
  "critical",
  "high",
  "abnormal",
  "watch",
  "slight",
  "normal",
];

const BAND_TONES: Record<AnomalyBand, StatusTone> = {
  normal: "healthy",
  slight: "healthy",
  watch: "caution",
  abnormal: "warning",
  high: "warning",
  critical: "critical",
};

/**
 * A band's colour — and `neutral` when there is no band.
 *
 * Deliberately not `healthy`. An unscored feature is not a feature that came
 * back fine, and colouring it green is how a machine nobody has learned a
 * normal for ends up looking like the healthiest thing on the plant.
 */
export function toneForBand(band: AnomalyBand | null): StatusTone {
  return band ? BAND_TONES[band] : "neutral";
}

/**
 * What to put where a score goes.
 *
 * An em dash, not a zero. `score ?? 0` would say "perfectly ordinary" about a
 * reading nothing has ever been compared to.
 *
 * `is_scored` is optional because an alarm does not carry one — a feature
 * with no score cannot alarm, so the engine never produces that pair. Where
 * it is absent, a score that exists is a score that counts.
 */
export function formatScore(feature: {
  score: number | null;
  is_scored?: boolean;
}): string {
  const scored = feature.is_scored ?? feature.score !== null;
  if (!scored || feature.score === null) return "—";
  return feature.score.toFixed(0);
}

export function formatConfidence(confidence: number | null): string {
  if (confidence === null || Number.isNaN(confidence)) return "—";
  return `${Math.round(confidence * 100)}%`;
}

/**
 * How unusual, in the direction it went.
 *
 * The sign is kept because a bearing band that collapses is as interesting as
 * one that climbs, and "3.2σ" alone loses the difference between a machine
 * getting worse and a sensor falling off.
 */
export function formatDeviation(z: number | null): string {
  if (z === null || Number.isNaN(z)) return "—";
  const magnitude = Math.abs(z).toFixed(1);
  return `${magnitude}σ ${z >= 0 ? "above" : "below"}`;
}

export interface BandTally {
  band: AnomalyBand;
  count: number;
}

/**
 * How many readings landed in each band, worst first.
 *
 * Unscored readings are not counted in any band — they are reported
 * separately by `CaptureScores.unscored`. Folding them into "normal" would be
 * the same lie one level up.
 */
export function tallyBands(scores: FeatureScore[]): BandTally[] {
  const counts = new Map<AnomalyBand, number>();
  for (const score of scores) {
    if (!score.is_scored || !score.band) continue;
    counts.set(score.band, (counts.get(score.band) ?? 0) + 1);
  }
  return BAND_ORDER.filter((band) => counts.has(band)).map((band) => ({
    band,
    count: counts.get(band) ?? 0,
  }));
}

/**
 * One line summarising a capture, for somebody who will read nothing else.
 *
 * It always says how many features could not be scored, because a capture
 * where most of them could not is a very different thing from a clean one and
 * the headline is the only place many people will look.
 */
export function summariseCapture(capture: CaptureScores): string {
  if (capture.scored === 0) {
    return capture.unscored > 0
      ? `Nothing could be scored on this capture — no learned normal for any of its ${capture.unscored} features.`
      : "This capture has no features to score.";
  }

  const worst = capture.worst;
  const unscored =
    capture.unscored > 0
      ? ` ${capture.unscored} feature${capture.unscored === 1 ? "" : "s"} could not be scored.`
      : "";

  if (!worst || worst.score === null || !worst.band) {
    return `${capture.scored} readings scored.${unscored}`;
  }

  return (
    `Worst reading: ${worst.feature_code} on channel ${worst.channel} at ` +
    `${worst.score.toFixed(0)} (${BAND_LABELS[worst.band].toLowerCase()}), ` +
    `out of ${capture.scored} scored.${unscored}`
  );
}

export const PROFILE_LABELS: Record<SensitivityProfile, string> = {
  conservative: "Conservative",
  balanced: "Balanced",
  early_warning: "Early warning",
  expert: "Expert",
};

export const PROFILE_BLURBS: Record<SensitivityProfile, string> = {
  conservative:
    "Fewer alarms, and later. Suits a machine whose failure is inconvenient rather than costly.",
  balanced: "The recommended setting for most machines.",
  early_warning:
    "Reacts sooner and accepts a thinner baseline. Being told early about a critical machine is worth being wrong more often.",
  expert: "Your own thresholds, within bounds that keep the engine usable.",
};

/**
 * Why a finding is not ringing, in words somebody can act on.
 *
 * The two reasons have different fixes — one is waiting, the other is a
 * baseline problem — so they must not collapse into "suppressed".
 */
export function explainHeldBack(alarm: HeldBackAlarm): string {
  if (alarm.held_back === "not_persistent") {
    return `Past the line for ${alarm.run_length} of the ${alarm.required} captures this machine's setting requires. Watching.`;
  }
  return `Sustained, but the normal it was measured against is too thin to act on (${formatConfidence(alarm.confidence)} confidence).`;
}

export const CONDITION_LABELS: Record<keyof AlarmConditions, string> = {
  repetition: "Repeated",
  rising: "Rising",
  steady_speed: "Steady speed",
  trustworthy: "Trusted baseline",
};

/** The conditions in a fixed order, so the row reads the same every time. */
export const CONDITION_ORDER: (keyof AlarmConditions)[] = [
  "repetition",
  "rising",
  "steady_speed",
  "trustworthy",
];

/**
 * Why a ringing alarm is not escalating.
 *
 * Named rather than counted: "two of four" tells nobody anything, and which
 * two it is decides what to do about it. A finding that never climbed is a
 * level sitting high; one taken while the speed was swinging is a
 * measurement to repeat.
 */
export function explainNotEscalating(alarm: Alarm): string | null {
  if (alarm.escalating) return null;
  const missing = CONDITION_ORDER.filter((key) => !alarm.conditions[key]).map(
    (key) => CONDITION_LABELS[key].toLowerCase(),
  );
  if (missing.length === 0) return null;
  return `Sustained, not worsening — ${missing.join(" and ")} missing.`;
}

/** How long a fault has been running, from when it first rang. */
export function formatDuration(since: string | null, now: Date = new Date()): string {
  if (!since) return "—";
  const started = new Date(since);
  if (Number.isNaN(started.getTime())) return "—";

  const minutes = Math.floor((now.getTime() - started.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr`;

  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
}

/**
 * Ringing alarms, worst first.
 *
 * Ranked by score rather than by confidence: how unusual something is decides
 * the order, and how sure we are is shown beside it so somebody can discount
 * it themselves. An unacknowledged alarm outranks an acknowledged one of the
 * same score, because it is the one nobody has looked at yet.
 */
export function rankAlarms(alarms: Alarm[]): Alarm[] {
  return [...alarms].sort((a, b) => {
    const seen = Number(Boolean(a.acknowledged_at)) - Number(Boolean(b.acknowledged_at));
    if (seen !== 0) return seen;
    // A fault getting worse outranks a higher reading that has been flat for
    // a month. Ordered on score alone the climbing one gets buried.
    const worsening = Number(b.escalating) - Number(a.escalating);
    if (worsening !== 0) return worsening;
    return (b.score ?? 0) - (a.score ?? 0);
  });
}

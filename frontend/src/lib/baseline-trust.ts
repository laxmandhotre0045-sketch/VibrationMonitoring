import type { BaselineHealth } from "@/types/baseline";

/**
 * How far the learned baseline in force can be leaned on.
 *
 * Derived from the structured fields the health endpoint returns, never by
 * re-deciding what the backend already decided. The sentences shown to the
 * reader are the backend's own `warnings`, which arrive worst-first and are
 * meant to be displayed as written; this only picks the headline.
 *
 * `none` is a verdict, not the absence of one. A sensor with no baseline in
 * force is the case the whole feature exists for — it is not trustworthy yet,
 * and saying nothing would leave that implicit.
 */
export type BaselineTrust = "none" | "building" | "weak" | "provisional" | "sound";

export interface BaselineTrustVerdict {
  trust: BaselineTrust;
  /** One line, suitable as the headline. */
  headline: string;
  /** The backend's sentences, worst first, shown as written. */
  reasons: string[];
  /** True while nothing should be judged against this baseline. */
  blocksComparison: boolean;
}

const HEADLINES: Record<BaselineTrust, string> = {
  none: "No baseline in force",
  building: "Baseline still being built",
  weak: "Baseline not trustworthy yet",
  provisional: "Baseline usable, with caveats",
  sound: "Baseline looks sound",
};

/**
 * True when the baseline has too little behind it to carry a finding.
 *
 * Two independent ways to be thin, and either is enough: learned from fewer
 * captures than the engine's own minimum, or holding features that scored at
 * or below its low-confidence threshold. Both numbers and both thresholds come
 * from the payload, so a recalibration on the backend moves this with it.
 */
function isWeak(health: BaselineHealth): boolean {
  const { samples, confidence, coverage } = health;

  const tooFewCaptures =
    samples.median !== null && samples.median < samples.minimum_required;

  // "Most features scored badly" rather than "any did": one weak feature out of
  // forty-six is a caveat, not a reason to distrust the whole baseline.
  const mostlyLowConfidence =
    coverage.rows > 0 && confidence.low_confidence_rows > coverage.rows / 2;

  return tooFewCaptures || mostlyLowConfidence;
}

export function assessBaselineTrust(
  health: BaselineHealth | null | undefined
): BaselineTrustVerdict {
  if (!health) {
    return {
      trust: "none",
      headline: HEADLINES.none,
      reasons: [],
      blocksComparison: true,
    };
  }

  if (!health.available) {
    // A version that exists but was never activated is a different situation
    // from no version at all, and the backend's `reason` says which. Both are
    // "nothing is being judged against this", so both block.
    const building = health.version?.state === "building";
    const trust: BaselineTrust = building ? "building" : "none";
    return {
      trust,
      headline: HEADLINES[trust],
      reasons: health.reason ? [health.reason] : [],
      blocksComparison: true,
    };
  }

  if (isWeak(health)) {
    return {
      trust: "weak",
      headline: HEADLINES.weak,
      reasons: health.warnings,
      // Available, so comparison happens; the point is that it should not be
      // trusted, not that it is switched off.
      blocksComparison: false,
    };
  }

  const trust: BaselineTrust = health.warnings.length > 0 ? "provisional" : "sound";
  return {
    trust,
    headline: HEADLINES[trust],
    reasons: health.warnings,
    blocksComparison: false,
  };
}

/** Captures behind the baseline, as a sentence, or null when unknown. */
export function describeSampleDepth(health: BaselineHealth): string | null {
  const { median, minimum_required, preferred } = health.samples;
  if (median === null) return null;
  return `${median.toFixed(0)} captures at the median (${minimum_required} required, ${preferred} preferred)`;
}

/** Channel-feature pairs covered, as a sentence, or null when unknowable. */
export function describeCoverage(health: BaselineHealth): string | null {
  const { rows, expected_rows, fraction } = health.coverage;
  if (fraction === null || expected_rows === null) return null;
  return `${rows} of ${expected_rows} channel-feature pairs (${Math.round(fraction * 100)}%)`;
}

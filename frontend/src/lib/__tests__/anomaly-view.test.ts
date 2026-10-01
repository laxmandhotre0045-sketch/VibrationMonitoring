import { describe, expect, it } from "vitest";

import {
  BAND_ORDER,
  CONDITION_ORDER,
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
import type {
  Alarm,
  CaptureScores,
  FeatureScore,
  HeldBackAlarm,
} from "@/types/anomaly";

/**
 * Turning Phase 2's numbers into something readable, without losing what they
 * mean.
 *
 * Most of this file defends one distinction: **a feature nothing could score
 * is not a feature that scored zero.** The backend is careful about it, the
 * API keeps it, and the presentation layer is the easiest place to throw it
 * away by accident — `score ?? 0` is one keystroke, and it turns "nobody has
 * ever learned a normal for this" into "perfectly ordinary".
 */

function scored(overrides: Partial<FeatureScore> = {}): FeatureScore {
  return {
    channel: 0,
    feature_code: "rms",
    score: 82,
    band: "high",
    is_scored: true,
    z_score: 3.9,
    confidence: 0.9,
    baseline_version: 7,
    mode_id: null,
    reason: null,
    contributions: {},
    ...overrides,
  };
}

function unscored(overrides: Partial<FeatureScore> = {}): FeatureScore {
  return scored({
    score: null,
    band: null,
    is_scored: false,
    z_score: null,
    confidence: 0,
    ...overrides,
  });
}

describe("an unscored reading is never shown as a zero", () => {
  it("renders a dash rather than a number", () => {
    expect(formatScore(unscored())).toBe("—");
    expect(formatScore(scored({ score: 0, band: "normal" }))).toBe("0");
  });

  it("is not coloured as healthy", () => {
    // Green would make a machine nobody has learned a normal for look like
    // the healthiest thing on the plant.
    expect(toneForBand(null)).toBe("neutral");
    expect(toneForBand("normal")).toBe("healthy");
  });

  it("is counted in no band at all", () => {
    const tally = tallyBands([scored(), unscored(), unscored()]);
    const total = tally.reduce((sum, row) => sum + row.count, 0);
    expect(total).toBe(1);
    expect(tally.find((row) => row.band === "normal")).toBeUndefined();
  });

  it("is reported in the headline rather than quietly dropped", () => {
    const capture: CaptureScores = {
      upload_id: "u",
      sensor_id: "s",
      scored: 1,
      unscored: 74,
      mode_id: null,
      mode_label: "normal_running",
      worst: scored(),
      scores: [],
    };
    expect(summariseCapture(capture)).toContain("74 features could not be scored");
  });

  it("says so plainly when nothing at all could be scored", () => {
    const capture: CaptureScores = {
      upload_id: "u",
      sensor_id: "s",
      scored: 0,
      unscored: 46,
      mode_id: null,
      mode_label: null,
      worst: null,
      scores: [],
    };
    const summary = summariseCapture(capture);
    expect(summary).toContain("Nothing could be scored");
    expect(summary).not.toContain("0 (");
  });
});

describe("the direction of a deviation survives", () => {
  it("keeps above and below apart", () => {
    // A bearing band that collapses is as interesting as one that climbs.
    expect(formatDeviation(3.2)).toBe("3.2σ above");
    expect(formatDeviation(-3.2)).toBe("3.2σ below");
  });

  it("has nothing to say when there is no deviation to report", () => {
    expect(formatDeviation(null)).toBe("—");
  });
});

describe("bands", () => {
  it("are ordered worst first, which is the order a screen shows them", () => {
    expect(BAND_ORDER[0]).toBe("critical");
    expect(BAND_ORDER[BAND_ORDER.length - 1]).toBe("normal");
  });

  it("are tallied worst first and omit the empty ones", () => {
    const tally = tallyBands([
      scored({ band: "normal" }),
      scored({ band: "critical" }),
      scored({ band: "normal" }),
    ]);
    expect(tally.map((row) => row.band)).toEqual(["critical", "normal"]);
    expect(tally[1].count).toBe(2);
  });
});

describe("confidence is shown, never folded into the score", () => {
  it("is a percentage of its own", () => {
    expect(formatConfidence(0.4)).toBe("40%");
    expect(formatConfidence(null)).toBe("—");
  });
});

describe("alarms", () => {
  function alarm(overrides: Partial<Alarm> = {}): Alarm {
    return {
      channel: 0,
      feature_code: "rms",
      score: 80,
      band: "high",
      confidence: 0.9,
      escalating: false,
      conditions: {
        repetition: true,
        rising: false,
        steady_speed: true,
        trustworthy: true,
      },
      stability: "steady",
      run_length: 4,
      required: 3,
      first_alarmed_at: "2026-09-26T10:00:00Z",
      last_alarmed_at: null,
      acknowledged_at: null,
      acknowledged_by: null,
      reason: null,
      ...overrides,
    };
  }

  it("are ranked by how unusual, not by how sure", () => {
    // Confidence is shown beside the rank so somebody can discount it
    // themselves; it does not decide the order.
    const ranked = rankAlarms([
      alarm({ feature_code: "b", score: 50, confidence: 1 }),
      alarm({ feature_code: "a", score: 90, confidence: 0.2 }),
    ]);
    expect(ranked[0].feature_code).toBe("a");
  });

  it("put what nobody has looked at above what somebody has", () => {
    const ranked = rankAlarms([
      alarm({ feature_code: "seen", score: 95, acknowledged_at: "2026-09-26T11:00:00Z" }),
      alarm({ feature_code: "new", score: 70 }),
    ]);
    expect(ranked[0].feature_code).toBe("new");
  });

  it("report how long the fault has been running", () => {
    const now = new Date("2026-09-26T13:30:00Z");
    expect(formatDuration("2026-09-26T10:00:00Z", now)).toBe("3 hr");
    expect(formatDuration("2026-09-24T10:00:00Z", now)).toBe("2 days");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("a held-back finding explains which kind it is", () => {
  function held(reason: HeldBackAlarm["held_back"]): HeldBackAlarm {
    return {
      channel: 1,
      feature_code: "peak",
      score: 95,
      band: "critical",
      confidence: 0.2,
      escalating: false,
      conditions: {
        repetition: false,
        rising: false,
        steady_speed: true,
        trustworthy: false,
      },
      stability: "steady",
      run_length: 1,
      required: 3,
      first_alarmed_at: null,
      last_alarmed_at: null,
      acknowledged_at: null,
      acknowledged_by: null,
      reason: null,
      held_back: reason,
    };
  }

  it("distinguishes waiting from a thin baseline", () => {
    // The two have different fixes, so they must not collapse into
    // "suppressed".
    expect(explainHeldBack(held("not_persistent"))).toContain("1 of the 3");
    expect(explainHeldBack(held("low_confidence"))).toContain("too thin");
  });
});


describe("the four conditions behind an escalation", () => {
  function alarm(overrides: Partial<Alarm> = {}): Alarm {
    return {
      channel: 0,
      feature_code: "rms",
      score: 80,
      band: "high",
      confidence: 0.9,
      escalating: false,
      conditions: {
        repetition: true,
        rising: true,
        steady_speed: true,
        trustworthy: true,
      },
      stability: "steady",
      run_length: 4,
      required: 3,
      first_alarmed_at: "2026-09-26T10:00:00Z",
      last_alarmed_at: null,
      acknowledged_at: null,
      acknowledged_by: null,
      reason: null,
      ...overrides,
    };
  }

  it("names which conditions were short, rather than counting them", () => {
    // "two of four" tells nobody anything; which two decides what to do.
    const explanation = explainNotEscalating(
      alarm({
        conditions: {
          repetition: true,
          rising: false,
          steady_speed: false,
          trustworthy: true,
        },
      }),
    );
    expect(explanation).toContain("rising");
    expect(explanation).toContain("steady speed");
  });

  it("says nothing when the alarm is escalating", () => {
    expect(explainNotEscalating(alarm({ escalating: true }))).toBeNull();
  });

  it("keeps the conditions in a fixed order so the row reads the same", () => {
    expect(CONDITION_ORDER).toEqual([
      "repetition",
      "rising",
      "steady_speed",
      "trustworthy",
    ]);
  });

  it("puts a worsening fault above a higher one that has been flat", () => {
    // Ordered on score alone, the climbing fault gets buried under a
    // reading that has not moved in a month.
    const ranked = rankAlarms([
      alarm({ feature_code: "flat", score: 99, escalating: false }),
      alarm({ feature_code: "climbing", score: 80, escalating: true }),
    ]);
    expect(ranked[0].feature_code).toBe("climbing");
  });

  it("still puts an unseen alarm above an acknowledged escalating one", () => {
    // Somebody has already looked at the escalating one; nobody has looked
    // at the other.
    const ranked = rankAlarms([
      alarm({
        feature_code: "seen",
        score: 99,
        escalating: true,
        acknowledged_at: "2026-09-26T11:00:00Z",
      }),
      alarm({ feature_code: "new", score: 70, escalating: false }),
    ]);
    expect(ranked[0].feature_code).toBe("new");
  });
});

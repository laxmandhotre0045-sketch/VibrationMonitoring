/**
 * Whether a learned baseline can be leaned on — VIK-033.
 *
 * The rule under all of it: a baseline nobody can vouch for must never read as
 * a sound one. "No baseline in force" is a verdict to show, not a blank to
 * leave, because the implicit version of it is what this feature replaces.
 */
import { describe, expect, it } from "vitest";

import {
  assessBaselineTrust,
  describeCoverage,
  describeSampleDepth,
} from "@/lib/baseline-trust";
import type { BaselineHealth } from "@/types/baseline";

function health(over: Partial<BaselineHealth> = {}): BaselineHealth {
  return {
    sensor_id: "s1",
    available: true,
    reason: null,
    version: {
      version: 3,
      state: "active",
      reason: null,
      created_by: null,
      created_at: null,
      activated_at: null,
      frozen_at: null,
      superseded_at: null,
      superseded_by: null,
      age_days: 2,
    },
    coverage: {
      rows: 46,
      channels: [0],
      distinct_features: 46,
      expected_rows: 46,
      fraction: 1,
    },
    confidence: { min: 0.8, median: 0.9, max: 1, low_confidence_rows: 0, threshold: 0.5 },
    samples: {
      min: 40,
      median: 40,
      max: 40,
      minimum_required: 12,
      preferred: 30,
      below_preferred_rows: 0,
    },
    freshness: {
      window_start: null,
      window_end: null,
      age_days: 2,
      captures_since_window: 0,
      stale: false,
      outgrown: false,
      stale_after_days: 90,
    },
    exclusions: {
      quality_excluded_observations: 0,
      other_shape_observations: 0,
      mixed_population_rows: 0,
    },
    warnings: [],
    history: [],
    ...over,
  };
}

describe("a baseline that is not there", () => {
  it("is a verdict, not a blank", () => {
    // The implicit version of this is exactly what the ticket replaces.
    const verdict = assessBaselineTrust(null);
    expect(verdict.trust).toBe("none");
    expect(verdict.headline).toMatch(/no baseline/i);
    expect(verdict.blocksComparison).toBe(true);
  });

  it("carries the backend's reason when it is unavailable", () => {
    const verdict = assessBaselineTrust(
      health({ available: false, reason: "No baseline is in force for this sensor.", version: null })
    );
    expect(verdict.trust).toBe("none");
    expect(verdict.reasons).toEqual(["No baseline is in force for this sensor."]);
  });

  it("tells a baseline still being built apart from none at all", () => {
    // Different situations: one needs somebody to activate it, the other needs
    // data. A caller that treated them alike would give the wrong advice.
    const verdict = assessBaselineTrust(
      health({
        available: false,
        reason: "A version in `building` is deliberately not used.",
        version: { ...health().version!, state: "building" },
      })
    );
    expect(verdict.trust).toBe("building");
    expect(verdict.blocksComparison).toBe(true);
  });
});

describe("a baseline that is too thin to carry a finding", () => {
  it("is weak when it holds fewer captures than the engine's own minimum", () => {
    const verdict = assessBaselineTrust(
      health({ samples: { ...health().samples, median: 8, minimum_required: 12 } })
    );
    expect(verdict.trust).toBe("weak");
    expect(verdict.headline).toMatch(/not trustworthy/i);
  });

  it("uses the payload's threshold rather than a number of its own", () => {
    // Same median, a minimum the backend raised. The verdict has to move with
    // the recalibration, or the screen and the engine disagree.
    const thin = { ...health().samples, median: 20 };
    expect(assessBaselineTrust(health({ samples: { ...thin, minimum_required: 12 } })).trust).not.toBe("weak");
    expect(assessBaselineTrust(health({ samples: { ...thin, minimum_required: 30 } })).trust).toBe("weak");
  });

  it("is weak when most features scored at or below the confidence threshold", () => {
    const verdict = assessBaselineTrust(
      health({ confidence: { ...health().confidence, low_confidence_rows: 40 } })
    );
    expect(verdict.trust).toBe("weak");
  });

  it("is not weak over a handful of low-confidence features", () => {
    // One weak feature out of forty-six is a caveat, not grounds to distrust
    // the whole baseline.
    const verdict = assessBaselineTrust(
      health({
        confidence: { ...health().confidence, low_confidence_rows: 3 },
        warnings: ["3 feature(s) scored at or below 0.5 confidence."],
      })
    );
    expect(verdict.trust).toBe("provisional");
  });

  it("still lets the comparison run", () => {
    // The point is that it should not be trusted, not that it is switched off.
    const verdict = assessBaselineTrust(
      health({ samples: { ...health().samples, median: 4 } })
    );
    expect(verdict.blocksComparison).toBe(false);
  });
});

describe("a baseline that is usable", () => {
  it("is sound only when the engine flagged nothing", () => {
    expect(assessBaselineTrust(health()).trust).toBe("sound");
    expect(assessBaselineTrust(health()).reasons).toEqual([]);
  });

  it("is provisional as soon as there is anything to say", () => {
    const warnings = ["The window ended 200 days ago."];
    const verdict = assessBaselineTrust(health({ warnings }));
    expect(verdict.trust).toBe("provisional");
    expect(verdict.reasons).toEqual(warnings);
  });

  it("shows the backend's sentences as written, in the order given", () => {
    // They arrive worst-first and carry the numbers that make them actionable;
    // re-ranking or paraphrasing them here would lose that.
    const warnings = ["Worst thing.", "Next thing.", "Least thing."];
    expect(assessBaselineTrust(health({ warnings })).reasons).toEqual(warnings);
  });
});

describe("the supporting facts", () => {
  it("states sample depth against both thresholds", () => {
    expect(describeSampleDepth(health())).toBe(
      "40 captures at the median (12 required, 30 preferred)"
    );
  });

  it("says nothing about depth it cannot know", () => {
    // Null is not zero. "0 captures" would be a claim nobody made.
    expect(describeSampleDepth(health({ samples: { ...health().samples, median: null } }))).toBeNull();
  });

  it("states coverage as a fraction of what was expected", () => {
    const partial = health({
      coverage: { rows: 12, channels: [0], distinct_features: 12, expected_rows: 46, fraction: 12 / 46 },
    });
    expect(describeCoverage(partial)).toBe("12 of 46 channel-feature pairs (26%)");
  });

  it("says nothing about coverage when nobody said what to expect", () => {
    // A coverage of 100% invented from the rows that happen to exist would
    // report full coverage for a baseline holding three features.
    const unknown = health({
      coverage: { rows: 3, channels: [0], distinct_features: 3, expected_rows: null, fraction: null },
    });
    expect(describeCoverage(unknown)).toBeNull();
  });
});

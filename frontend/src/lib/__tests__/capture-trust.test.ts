/**
 * The capture trust verdict, from the wire to the badge.
 *
 * The rule the whole feature rests on is that absent is not a pass. A capture
 * nobody assessed is unexamined, and every step here has to keep saying so —
 * the normalizer must not invent a level, and the badge must not go blank.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { normalizeUploadFeaturesResponse } from "@/lib/feature-api-normalize";
import {
  CHECK_LABELS,
  formatCheckName,
} from "@/components/analysis/workspace/CaptureTrustBadge";

function normalize(payload: Record<string, unknown>) {
  return normalizeUploadFeaturesResponse(payload, { uploadId: "u1", channel: 0 });
}

describe("the trust level off the wire", () => {
  it("carries the four published levels through", () => {
    for (const level of ["High", "Medium", "Low", "Invalid"]) {
      expect(normalize({ trust_level: level }).trust_level).toBe(level);
    }
  });

  it("accepts the engine's lowercase spelling", () => {
    // The engine emits "high"; the contract publishes "High". A level that
    // failed to normalize would read as unassessed, which looks identical to a
    // capture nothing checked.
    expect(normalize({ trust_level: "high" }).trust_level).toBe("High");
    expect(normalize({ trust_level: "  INVALID  " }).trust_level).toBe("Invalid");
  });

  it("reports a missing verdict as no verdict, never as a pass", () => {
    expect(normalize({}).trust_level).toBeNull();
    expect(normalize({ trust_level: null }).trust_level).toBeNull();
  });

  it("refuses a level it cannot place in the ordering", () => {
    // Including the engine's own "unknown", which is what it reports when the
    // assessment itself could not run. That means unassessed, and it is not
    // one of the four a screen can switch on.
    for (const raw of ["unknown", "Excellent", "", "  ", 3, {}]) {
      expect(normalize({ trust_level: raw }).trust_level, String(raw)).toBeNull();
    }
  });
});

describe("the check lists", () => {
  it("keeps failures and unrunnable checks apart", () => {
    const result = normalize({
      trust_level: "Medium",
      failed_checks: ["clipping"],
      not_assessed_checks: ["unstable_speed"],
    });

    expect(result.failed_checks).toEqual(["clipping"]);
    expect(result.not_assessed_checks).toEqual(["unstable_speed"]);
  });

  it("defaults both to empty rather than undefined", () => {
    const result = normalize({ trust_level: "High" });
    expect(result.failed_checks).toEqual([]);
    expect(result.not_assessed_checks).toEqual([]);
  });

  it("refuses anything that is not a list", () => {
    // A bare string is the dangerous one: spreading it would list every letter
    // as a separate failed check.
    for (const raw of ["clipping", 7, null, {}]) {
      expect(normalize({ failed_checks: raw }).failed_checks, String(raw)).toEqual([]);
    }
  });

  it("reads a check reported as a record", () => {
    const result = normalize({
      failed_checks: [{ code: "clipping", message: "12% of samples at full scale" }],
    });
    expect(result.failed_checks).toEqual(["clipping"]);
  });

  it("drops blanks and repeats", () => {
    // A check listed twice reads as two separate problems.
    const result = normalize({ failed_checks: ["clipping", "clipping", "", "  ", null] });
    expect(result.failed_checks).toEqual(["clipping"]);
  });
});

describe("check names on screen", () => {
  it("reads every check the engine can report as words", () => {
    const engineChecks = [
      "missing_data",
      "clipping",
      "saturation",
      "loose_sensor",
      "unstable_speed",
      "bias_drift",
      "noise_floor",
      "dc_offset",
    ];

    for (const check of engineChecks) {
      const label = formatCheckName(check);
      expect(label, check).not.toContain("_");
      expect(label.trim().length, check).toBeGreaterThan(0);
      expect(label[0], check).toBe(label[0].toUpperCase());
    }
  });

  it("still renders a check it has never heard of", () => {
    // Hiding an unrecognised check would hide a real finding; the slug just
    // has to stop looking like a slug.
    expect(formatCheckName("some_new_check")).toBe("Some new check");
  });
});

// ---------------------------------------------------------------------------
// The engine, which decides the checks
// ---------------------------------------------------------------------------

const QUALITY_ENGINE = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "..",
  "backend",
  "app",
  "ai",
  "quality.py"
);

/**
 * Every check name the engine can put in `failed_checks`.
 *
 * Reaching into the Python is unusual for a frontend test, but the badge's
 * label map exists only to mirror this list. Skipped when the backend is not
 * checked out beside the frontend, so a frontend-only clone still runs green.
 */
function engineCheckNames(): string[] {
  const source = readFileSync(QUALITY_ENGINE, "utf8");
  const names = new Set<string>();
  for (const match of source.matchAll(
    /(?:Check\(\s*|_passed\(|_not_applicable\(|_failed\()"([a-z_]+)"/g
  )) {
    names.add(match[1]);
  }
  return [...names];
}

describe.skipIf(!existsSync(QUALITY_ENGINE))("the quality engine's checks", () => {
  it("was found and parsed", () => {
    // Guards the guard: an empty list would make the next test pass without
    // checking anything.
    expect(engineCheckNames().length).toBeGreaterThan(0);
  });

  it("has a written-out label for every check it can report", () => {
    // Asserted against the map rather than against the rendered string. Some
    // labels match what the generic formatter would produce anyway — "Bias
    // drift" is one — so comparing the output cannot tell a chosen label from
    // a fall-through, and would fail on wording that is perfectly good.
    const unlabelled = engineCheckNames().filter(
      (name) => !Object.prototype.hasOwnProperty.call(CHECK_LABELS, name)
    );
    expect(unlabelled, "these checks have no label of their own").toEqual([]);
  });

  it("labels nothing the engine cannot report", () => {
    // A label for a check that no longer exists is dead copy that reads as if
    // the check were still running.
    const known = new Set(engineCheckNames());
    const stale = Object.keys(CHECK_LABELS).filter((name) => !known.has(name));
    expect(stale, "these labels describe checks the engine no longer has").toEqual([]);
  });
});

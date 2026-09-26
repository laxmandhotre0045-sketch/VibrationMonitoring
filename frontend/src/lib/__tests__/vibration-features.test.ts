/**
 * The shared feature catalog.
 *
 * This module is a list, which is why it looks like it needs no tests. It is
 * also the only place three things agree: the Settings page builds its
 * threshold grid from it, the Status (Health) tab groups its rows by it, and
 * the API normalizer uses it to turn backend feature codes into labels. Adding
 * a feature, renaming a label or introducing a category touches all three, and
 * none of them fail loudly when the agreement breaks — a feature simply stops
 * appearing, which looks like a machine with nothing to report.
 *
 * So these tests are mostly about the seams rather than the functions.
 */
import { describe, expect, it } from "vitest";

import {
  FACTOR_TREND_KEYS,
  FEATURE_CATEGORY_LABELS,
  FEATURE_CATEGORY_ORDER,
  VIBRATION_FEATURE_CATALOG,
  formatFeatureUnit,
  getFeatureDefinition,
  resolveVibrationFeatureKey,
  type VibrationFeatureKey,
} from "@/lib/vibration-features";

const KEYS = VIBRATION_FEATURE_CATALOG.map((def) => def.key);
const KEY_SET = new Set<string>(KEYS);

/** Non-ASCII spelled out, so an encoding accident cannot quietly pass. */
const EM_DASH = "—";
const SUPERSCRIPT_TWO = "²";

// ---------------------------------------------------------------------------
// The catalog
// ---------------------------------------------------------------------------

describe("the catalog", () => {
  it("is exactly these forty-six features, in this order", () => {
    // Written out rather than derived on purpose. Everything else here checks
    // the catalog against itself and would happily follow a mistake; this is
    // the one assertion that makes adding, removing or reordering a feature a
    // deliberate act with a matching test edit.
    //
    // Grouped by category, which is the order the Status tab and the Settings
    // grid render. The backend's own list is ordered by when each feature was
    // added, and the contract test next door checks the two cover each other
    // as sets rather than in step.
    expect(KEYS).toEqual([
      // time_domain
      "rms",
      "peak",
      "crest_factor",
      "kurtosis",
      "peak_to_peak",
      "std_dev",
      "skewness",
      "impulse_factor",
      "shape_factor",
      "clearance_factor",
      "burst_count",
      "shock_index",
      "modulation_index",
      "rms_change_short",
      "rms_change_long",
      "zero_crossing_rate",
      "dc_offset",
      // frequency_domain
      "fft_band_energy",
      "amplitude_1x",
      "amplitude_2x",
      "amplitude_3x",
      "dominant_frequency",
      "dominant_prominence",
      "harmonic_count",
      "harmonic_energy_ratio",
      "sideband_spacing",
      "sideband_energy_ratio",
      "spectral_centroid",
      "spectral_spread",
      "spectral_entropy",
      "broadband_noise",
      "haystack_score",
      "narrowband_ratio",
      "peak_drift",
      // envelope
      "envelope_rms",
      "ftf_band_energy",
      "bsf_band_energy",
      "bpfo_band_energy",
      "bpfi_band_energy",
      "bearing_harmonic_energy",
      "envelope_peak",
      "envelope_kurtosis",
      "demodulated_peak_prominence",
      "repetition_impact_frequency",
      "resonance_band_energy",
      // noise
      "noise_floor",
    ]);
  });

  it("has no duplicate keys", () => {
    expect(KEY_SET.size).toBe(KEYS.length);
  });

  it("gives every feature a distinct label", () => {
    // Two features sharing a label are two rows a user cannot tell apart, in
    // both the threshold grid and the health table.
    const labels = VIBRATION_FEATURE_CATALOG.map((def) => def.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.every((label) => label.trim().length > 0)).toBe(true);
  });

  it("gives every feature a unit", () => {
    // "-" is the deliberate "no unit" marker; empty is just missing.
    expect(VIBRATION_FEATURE_CATALOG.every((def) => def.unit.length > 0)).toBe(true);
  });

  it("exposes the same keys as FACTOR_TREND_KEYS", () => {
    expect(FACTOR_TREND_KEYS).toEqual(KEYS);
  });
});

// ---------------------------------------------------------------------------
// Categories — the grouping both screens rely on
// ---------------------------------------------------------------------------

describe("categories", () => {
  it("orders every category the catalog actually uses", () => {
    // This is the silent break the ticket is about. Both screens iterate
    // FEATURE_CATEGORY_ORDER and keep the features that match; a feature in a
    // category missing from that list is not an error anywhere — it is simply
    // never rendered, on either screen.
    const used = new Set(VIBRATION_FEATURE_CATALOG.map((def) => def.category));
    const ordered = new Set(FEATURE_CATEGORY_ORDER);
    const unreachable = [...used].filter((category) => !ordered.has(category));

    expect(unreachable, "these categories would never be rendered").toEqual([]);
  });

  it("names every ordered category", () => {
    // A missing label renders a group heading as "undefined".
    for (const category of FEATURE_CATEGORY_ORDER) {
      expect(FEATURE_CATEGORY_LABELS[category], `no label for ${category}`).toBeTruthy();
    }
  });

  it("lists no category twice", () => {
    // A repeated category renders the same group, with the same rows, twice.
    expect(new Set(FEATURE_CATEGORY_ORDER).size).toBe(FEATURE_CATEGORY_ORDER.length);
  });

  it("puts time-domain features first", () => {
    // The order is the reading order on both screens: the four cheap
    // time-domain numbers before anything derived from a spectrum.
    expect(FEATURE_CATEGORY_ORDER[0]).toBe("time_domain");
  });
});

// ---------------------------------------------------------------------------
// resolveVibrationFeatureKey
// ---------------------------------------------------------------------------

describe("resolveVibrationFeatureKey", () => {
  it("resolves every key to itself", () => {
    for (const key of KEYS) {
      expect(resolveVibrationFeatureKey(key), key).toBe(key);
    }
  });

  it("resolves every label back to its key", () => {
    // The API is not the only caller: anything that has already been through
    // the normalizer holds a label, and round-tripping it must not lose the
    // feature. "FFT Band Energy (0-500 Hz)" is the interesting one.
    for (const def of VIBRATION_FEATURE_CATALOG) {
      expect(resolveVibrationFeatureKey(def.label), def.label).toBe(def.key);
    }
  });

  it("resolves the codes the backend actually sends", () => {
    // These are the literals in backend/app/services/feature_extraction.py.
    // Only one differs from the frontend key, and it is the whole reason the
    // alias table exists.
    expect(resolveVibrationFeatureKey("fft_band_energy_0_500")).toBe("fft_band_energy");
    expect(resolveVibrationFeatureKey("crest_factor")).toBe("crest_factor");
    expect(resolveVibrationFeatureKey("noise_floor")).toBe("noise_floor");
  });

  it.each([
    ["  RMS  ", "rms"],
    ["Crest-Factor", "crest_factor"],
    ["crest factor", "crest_factor"],
    ["CrestFactor", "crest_factor"],
    ["1X", "amplitude_1x"],
    ["1x_amplitude", "amplitude_1x"],
    ["Amplitude1X", "amplitude_1x"],
    ["2x", "amplitude_2x"],
    ["3X Amplitude", "amplitude_3x"],
    ["envelope rms", "envelope_rms"],
    ["Noise Floor", "noise_floor"],
    ["FFT Band Energy (0-500 Hz)", "fft_band_energy"],
  ])("reads %j as %j", (raw, expected) => {
    expect(resolveVibrationFeatureKey(raw)).toBe(expected);
  });

  it.each([null, undefined, "", "   "])("returns null for %j", (raw) => {
    expect(resolveVibrationFeatureKey(raw)).toBeNull();
  });

  it("returns null for a feature it does not know", () => {
    // Callers branch on null to fall back to the raw name, so a wrong answer
    // here is worse than no answer.
    expect(resolveVibrationFeatureKey("bearing_temperature")).toBeNull();
    expect(resolveVibrationFeatureKey("amplitude_4x")).toBeNull();
    expect(resolveVibrationFeatureKey("4x")).toBeNull();
  });

  it("does not mistake an inherited object property for a feature", () => {
    // The alias table is a plain object, so `aliases[token]` also searches
    // Object.prototype. Lowercasing hides most of it — "toString" normalizes
    // to "tostring", which is not inherited — but "constructor" survives
    // intact and its inherited value is truthy. That used to come back as if
    // it were a feature key: getFeatureDefinition would then find nothing and
    // the Status tab would read .label off undefined.
    for (const inherited of [
      "constructor",
      "toString",
      "valueOf",
      "hasOwnProperty",
      "isPrototypeOf",
      "__proto__",
    ]) {
      expect(resolveVibrationFeatureKey(inherited), inherited).toBeNull();
    }
  });

  it("never answers with something outside the catalog", () => {
    // The guarantee every caller leans on: whatever comes back is either null
    // or a key getFeatureDefinition can look up.
    const probes = [
      "constructor",
      "prototype",
      "__defineGetter__",
      "",
      "-",
      "___",
      "RMS!!!",
      "énergie",
      "rms rms",
      "0",
    ];
    for (const probe of probes) {
      const resolved = resolveVibrationFeatureKey(probe);
      expect(
        resolved === null || KEY_SET.has(resolved),
        `${probe} -> ${String(resolved)}`
      ).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// getFeatureDefinition and formatFeatureUnit
// ---------------------------------------------------------------------------

describe("getFeatureDefinition", () => {
  it("finds every key in the catalog", () => {
    for (const def of VIBRATION_FEATURE_CATALOG) {
      expect(getFeatureDefinition(def.key)).toEqual(def);
    }
  });

  it("agrees with whatever resolve returned", () => {
    // The pairing that matters: resolve, then look up, with nothing in between
    // able to produce a miss.
    for (const raw of ["fft_band_energy_0_500", "Crest Factor", "1X", "  peak  "]) {
      const key = resolveVibrationFeatureKey(raw);
      expect(key).not.toBeNull();
      expect(getFeatureDefinition(key as VibrationFeatureKey)).toBeDefined();
    }
  });

  it("returns undefined for a key that is not in the catalog", () => {
    // Recorded rather than endorsed. The signature promises a definition and
    // the `!` inside says "trust me", so an unknown key is a crash at the
    // caller's first property read rather than here. Types stop that at
    // compile time; API data cast to the key type is the way around it, which
    // is why resolve above must never hand out a key the catalog lacks.
    const notAKey = "bearing_temperature" as VibrationFeatureKey;
    expect(getFeatureDefinition(notAKey)).toBeUndefined();
  });
});

describe("formatFeatureUnit", () => {
  it.each(["-", "", undefined, null])("renders %j as an em dash", (unit) => {
    expect(formatFeatureUnit(unit as string | undefined)).toBe(EM_DASH);
  });

  it("passes a real unit through untouched", () => {
    expect(formatFeatureUnit("dB")).toBe("dB");
    expect(formatFeatureUnit("scaled")).toBe("scaled");
    expect(formatFeatureUnit(`scaled${SUPERSCRIPT_TWO}`)).toBe(`scaled${SUPERSCRIPT_TWO}`);
  });

  it("covers every unit in the catalog", () => {
    for (const def of VIBRATION_FEATURE_CATALOG) {
      expect(formatFeatureUnit(def.unit).length).toBeGreaterThan(0);
    }
  });
});

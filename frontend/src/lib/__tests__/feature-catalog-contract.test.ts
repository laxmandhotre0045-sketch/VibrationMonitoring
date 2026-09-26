/**
 * The catalog's three consumers, held to the same list.
 *
 * `vibration-features.ts` is tested on its own terms next door. This file is
 * about what the ticket actually worries about: the catalog is read by the
 * Settings page (as threshold columns) and by the Status tab (as health rows),
 * and fed by the backend's feature codes. None of those three break loudly.
 * Drop a feature from the catalog and the Settings grid quietly loses a column;
 * add one the backend never sends and the Status tab shows a permanent
 * "no baseline" row for a number nobody is computing.
 *
 * Each test below stands in for a screen, so a change to the list fails here
 * rather than in front of a user.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  VIBRATION_FEATURE_CATALOG,
  FEATURE_CATEGORY_LABELS,
  FEATURE_CATEGORY_ORDER,
  resolveVibrationFeatureKey,
} from "@/lib/vibration-features";
import {
  groupFeatureCompareItems,
  groupFeatureStatusItems,
} from "@/lib/feature-display";
import {
  THRESHOLD_PARAMETERS,
  type ThresholdParameter,
} from "@/types/vibration-settings";
import { formatThresholdParameterLabel } from "@/lib/vibration-settings-utils";
import type { FeatureStatusItem } from "@/types/features";

const CATALOG_KEYS = VIBRATION_FEATURE_CATALOG.map((def) => def.key);

// ---------------------------------------------------------------------------
// The Settings page
// ---------------------------------------------------------------------------

describe("the Settings threshold grid", () => {
  it("has one column per catalog feature, in catalog order", () => {
    // ThresholdCoverageMatrix maps over THRESHOLD_PARAMETERS for its header
    // and again for every channel row, so this list is literally the grid.
    expect(THRESHOLD_PARAMETERS.map((param) => param.id)).toEqual(CATALOG_KEYS);
  });

  it("carries the catalog's labels and categories across unchanged", () => {
    for (const def of VIBRATION_FEATURE_CATALOG) {
      const param = THRESHOLD_PARAMETERS.find((item) => item.id === def.key);
      expect(param, `no threshold column for ${def.key}`).toBeDefined();
      expect(param?.label).toBe(def.label);
      expect(param?.category).toBe(def.category);
    }
  });

  it("turns the catalog's no-unit marker into an empty unit", () => {
    // The catalog writes "-" for dimensionless; Settings appends the unit to
    // the label, so carrying "-" through would print "Crest Factor (-)".
    const crest = THRESHOLD_PARAMETERS.find((param) => param.id === "crest_factor");
    expect(crest?.unit).toBe("");
    expect(THRESHOLD_PARAMETERS.every((param) => param.unit !== "-")).toBe(true);
  });

  it("builds a readable column heading for every feature", () => {
    for (const param of THRESHOLD_PARAMETERS) {
      const heading = formatThresholdParameterLabel(param.id);
      expect(heading.trim().length, `empty heading for ${param.id}`).toBeGreaterThan(0);
      expect(heading, `raw key leaked into the heading for ${param.id}`).not.toBe(param.id);
      expect(heading).not.toContain("(-)");
      expect(heading).not.toContain("undefined");
    }
  });

  it("does not nest parentheses on a label that already has them", () => {
    // FFT Band Energy (0-500 Hz) is the only such label today, and the branch
    // that handles it is keyed on the "(" in the catalog's label text.
    expect(formatThresholdParameterLabel("fft_band_energy")).toBe(
      "FFT Band Energy (0-500 Hz) · scaled²"
    );
    expect(formatThresholdParameterLabel("rms")).toBe("RMS (scaled)");
  });

  it("uses ids the resolver still recognises", () => {
    // Settings stores the parameter id; anything that reads those rows back
    // goes through the resolver to reach a definition.
    for (const param of THRESHOLD_PARAMETERS) {
      expect(resolveVibrationFeatureKey(param.id), param.id).toBe(param.id);
    }
  });
});

// ---------------------------------------------------------------------------
// The Status (Health) tab
// ---------------------------------------------------------------------------

/** Row shaped the way the API normalizer hands them over. */
function apiRow(feature: string, overrides: Partial<FeatureStatusItem> = {}): FeatureStatusItem {
  return { feature, value: 1, status: "normal", ...overrides };
}

function flatten(groups: { items: FeatureStatusItem[] }[]): FeatureStatusItem[] {
  return groups.flatMap((group) => group.items);
}

describe("the Status health table", () => {
  it("shows every catalog feature even when the API sends none", () => {
    // An upload with no baseline still has to render every row; a short list
    // reads as "this machine has fewer things to watch", which is not true.
    const rows = flatten(groupFeatureStatusItems([]));
    expect(rows.map((row) => row.feature_key)).toEqual(CATALOG_KEYS);
    expect(rows.every((row) => row.status === "no_baseline")).toBe(true);
  });

  it("groups under the catalog's category headings, in order", () => {
    const groups = groupFeatureStatusItems([]);
    expect(groups.map((group) => group.category)).toEqual([...FEATURE_CATEGORY_ORDER]);
    expect(groups.map((group) => group.label)).toEqual(
      FEATURE_CATEGORY_ORDER.map((category) => FEATURE_CATEGORY_LABELS[category])
    );
  });

  it("labels a backend feature code with the catalog's label and unit", () => {
    const rows = flatten(
      groupFeatureStatusItems([apiRow("fft_band_energy_0_500", { value: 0.42 })])
    );
    const fft = rows.find((row) => row.feature_key === "fft_band_energy");

    expect(fft?.feature).toBe("FFT Band Energy (0-500 Hz)");
    expect(fft?.unit).toBe("scaled²");
    expect(fft?.value).toBe(0.42);
  });

  it("keeps the rows the API did not send alongside the ones it did", () => {
    const rows = flatten(
      groupFeatureStatusItems([
        apiRow("rms", { value: 0.008, status: "warning" }),
        apiRow("crest_factor", { value: 4.1 }),
      ])
    );

    expect(rows).toHaveLength(CATALOG_KEYS.length);
    expect(rows.find((row) => row.feature_key === "rms")?.status).toBe("warning");
    expect(rows.find((row) => row.feature_key === "kurtosis")?.status).toBe("no_baseline");
  });

  it("drops a feature it cannot place rather than rendering it bare", () => {
    // A row with no category would be filtered out of every group anyway; the
    // point is that it does not arrive as an unlabelled extra row either.
    const rows = flatten(groupFeatureStatusItems([apiRow("bearing_temperature", { value: 71 })]));

    expect(rows).toHaveLength(CATALOG_KEYS.length);
    expect(rows.some((row) => row.feature === "bearing_temperature")).toBe(false);
  });

  it("prefers the API's own unit when it sends one", () => {
    const rows = flatten(groupFeatureStatusItems([apiRow("rms", { unit: "mm/s" })]));
    expect(rows.find((row) => row.feature_key === "rms")?.unit).toBe("mm/s");
  });

  it("treats the baseline comparison the same way", () => {
    // Same catalog, second table on the same screen.
    const groups = groupFeatureCompareItems([]);
    expect(groups.flatMap((group) => group.items).map((item) => item.feature_key)).toEqual(
      CATALOG_KEYS
    );
  });
});

// ---------------------------------------------------------------------------
// The two screens, against each other
// ---------------------------------------------------------------------------

describe("Settings and Status", () => {
  it("offer thresholds for exactly the features Status reports on", () => {
    // The invariant behind the whole module: a threshold with no health row is
    // a limit nobody checks, and a health row with no threshold can never be
    // anything but "no baseline".
    const settings = THRESHOLD_PARAMETERS.map((param) => param.id).sort();
    const status = flatten(groupFeatureStatusItems([]))
      .map((row) => row.feature_key as ThresholdParameter)
      .sort();

    expect(settings).toEqual(status);
  });
});

// ---------------------------------------------------------------------------
// The backend, which supplies the numbers
// ---------------------------------------------------------------------------

const BACKEND_ROOT = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "..",
  "backend",
  "app"
);

const BACKEND_FEATURE_EXTRACTION = join(BACKEND_ROOT, "services", "feature_extraction.py");

/**
 * The four files FEATURE_CODES is assembled from.
 *
 * It is not one literal: `feature_extraction.py` declares the original ten and
 * then appends three lists imported from `app.ai`. Reading only the first file
 * would report the other thirty-six as "on screen but nothing computes them",
 * which is the opposite of true.
 */
const BACKEND_CODE_SOURCES: [string, string][] = [
  [BACKEND_FEATURE_EXTRACTION, "FEATURE_CODES"],
  [join(BACKEND_ROOT, "ai", "time_features.py"), "TIME_FEATURE_CODES"],
  [join(BACKEND_ROOT, "ai", "frequency_features.py"), "FREQUENCY_FEATURE_CODES"],
  [join(BACKEND_ROOT, "ai", "envelope_features.py"), "ENVELOPE_FEATURE_CODES"],
];

/**
 * Read the backend's feature codes out of the Python.
 *
 * A frontend test reaching into the Python is unusual, but this catalog exists
 * to mirror that list and has no other reason to hold the entries it does.
 * Skipped when the backend is not checked out beside the frontend, so a
 * frontend-only clone still runs green.
 */
function backendFeatureCodes(): string[] {
  const codes: string[] = [];
  for (const [path, symbol] of BACKEND_CODE_SOURCES) {
    if (!existsSync(path)) continue;
    const source = readFileSync(path, "utf8");
    // String.raw, or the backslashes collapse in the template literal and the
    // pattern silently stops matching anything.
    const block = new RegExp(String.raw`${symbol}\s*=\s*\[([^\]]*)\]`).exec(source);
    if (!block) continue;
    for (const match of block[1].matchAll(/"([^"]+)"/g)) {
      if (!codes.includes(match[1])) codes.push(match[1]);
    }
  }
  return codes;
}

describe.skipIf(!existsSync(BACKEND_FEATURE_EXTRACTION))("the backend feature list", () => {
  it("was found and parsed, from all four of its sources", () => {
    // Guards the guard: a silently empty list would make the next two tests
    // pass without checking anything, and reading only the first file would
    // silently drop thirty-six codes.
    const codes = backendFeatureCodes();
    expect(codes.length).toBe(CATALOG_KEYS.length);
    for (const marker of ["rms", "peak_to_peak", "dominant_frequency", "ftf_band_energy"]) {
      expect(codes, `${marker} is missing, so a source file went unread`).toContain(marker);
    }
  });

  it("has every code resolving to a catalog feature", () => {
    const unresolved = backendFeatureCodes().filter(
      (code) => resolveVibrationFeatureKey(code) === null
    );
    expect(unresolved, "the backend computes these but no screen can show them").toEqual([]);
  });

  it("covers the catalog exactly, with nothing left over on either side", () => {
    const fromBackend = new Set(
      backendFeatureCodes()
        .map((code) => resolveVibrationFeatureKey(code))
        .filter((key): key is NonNullable<typeof key> => key !== null)
    );
    const missing = CATALOG_KEYS.filter((key) => !fromBackend.has(key));

    expect(missing, "these are on screen but nothing computes them").toEqual([]);
    expect(fromBackend.size).toBe(CATALOG_KEYS.length);
  });
});

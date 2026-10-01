/**
 * The mapping and the shipped library have to agree.
 *
 * `library-models.ts` says "a Pump is the end-suction pump, library id `es`".
 * The library is a 205 KB page built from the kit by a script nobody runs by
 * hand. Nothing in the type system connects the two, so the failure mode is
 * quiet: somebody rebuilds from a newer kit where a machine was renamed, the
 * mapping still compiles, and a plant engineer opens a pump to find an empty
 * stage and a chip list that never had `es` in it.
 *
 * So this reads the real `public/senvia-3d/library.html` and checks the ids we
 * claim against the ids it actually defines — plus the things the build script
 * promises about that file: the whole toolbar is present, and nothing reaches
 * for a CDN.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  LIBRARY_EQUIPMENT,
  MAPPED_MACHINE_TYPES,
  libraryIdForMachineType,
  libraryModel,
} from "../library-models";

const LIBRARY_HTML = join(
  dirname(fileURLToPath(import.meta.url)),
  "..", "..", "..", "..",
  "public", "senvia-3d", "library.html"
);

/** Every Machine Type the Equipment Master offers in Step 1. */
const MACHINE_TYPES = [
  "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
  "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
  "Spindle", "Wind Turbine",
];

/**
 * The library's own id table: `{es:'EQ-UTL-001', mill:'EQ-CMS-002', …}`, all 94
 * models. Parsing it is what lets this test check both halves of every entry —
 * the short id the viewer takes and the catalogue id the GLB is filed under.
 */
function readRegistry(): Record<string, string> {
  const html = readFileSync(LIBRARY_HTML, "utf8");
  const block = /const REG=\{([\s\S]*?)\};/.exec(html);
  if (!block) throw new Error("REG table not found in library.html");
  const entries: Record<string, string> = {};
  for (const [, id, modelId] of block[1].matchAll(/(\w+):'([A-Z]{2}-[A-Z]{3}-\d{3})'/g)) {
    entries[id] = modelId;
  }
  return entries;
}

describe("the 3D library is built", () => {
  it("is present in public/", () => {
    // Everything below reads this file. Without it the suite would pass by
    // testing nothing, on the one seam that has no compiler behind it.
    expect(
      existsSync(LIBRARY_HTML),
      "run: python senvia-3d/tools/build_web_library.py"
    ).toBe(true);
  });
});

describe("the mapping matches the shipped library", () => {
  const registry = readRegistry();
  const equipmentIds = Object.entries(registry)
    .filter(([, modelId]) => modelId.startsWith("EQ-"))
    .map(([id]) => id);

  it("lists every machine the library draws", () => {
    expect(LIBRARY_EQUIPMENT).toHaveLength(48);
    expect(equipmentIds).toHaveLength(48);
    expect([...LIBRARY_EQUIPMENT].map((m) => m.id).sort()).toEqual([...equipmentIds].sort());
  });

  it.each([...LIBRARY_EQUIPMENT])("$id is filed under $modelId", ({ id, modelId }) => {
    expect(registry[id]).toBe(modelId);
  });

  it("claims no machine the library does not have", () => {
    for (const model of LIBRARY_EQUIPMENT) {
      expect(registry, `${model.id} is not in the library`).toHaveProperty(model.id);
    }
  });
});

describe("every machine type reaches a real machine", () => {
  const registry = readRegistry();

  it.each(MACHINE_TYPES)("%s resolves", (machineType) => {
    const id = libraryIdForMachineType(machineType);
    // A null here would mean the viewer opens on whatever sorts first, which is
    // the behaviour this mapping exists to prevent.
    expect(id, `${machineType} has no library machine`).not.toBeNull();
    expect(registry[id!], `${machineType} -> ${id} is not in the library`).toMatch(/^EQ-/);
  });

  it("is case and whitespace insensitive", () => {
    // Step 1 writes "DG Set"; older rows carry "dg set" and worse.
    expect(libraryIdForMachineType("DG Set")).toBe("dg");
    expect(libraryIdForMachineType("dg set")).toBe("dg");
    expect(libraryIdForMachineType("  Pump  ")).toBe("es");
  });

  it("says so plainly when nothing matches", () => {
    // Null is the honest answer: the viewer then opens on the library's first
    // machine with all 48 reachable, rather than drawing a lie.
    expect(libraryIdForMachineType("Hydraulic Press")).toBeNull();
    expect(libraryIdForMachineType("")).toBeNull();
    expect(libraryIdForMachineType(null)).toBeNull();
    expect(libraryIdForMachineType(undefined)).toBeNull();
  });

  it("covers everything Step 1 offers", () => {
    const covered = new Set(MAPPED_MACHINE_TYPES);
    for (const machineType of MACHINE_TYPES) {
      expect(covered, `${machineType} is not in the map`).toContain(machineType.toLowerCase());
    }
  });

  it("resolves a blower to a positive-displacement machine, not a fan", () => {
    // A Roots blower's signature follows its lobes; a centrifugal fan's follows
    // its blades. Drawing one as the other would put the wrong orders on screen
    // next to a real spectrum.
    expect(libraryModel(libraryIdForMachineType("Blower"))?.name).toBe("Roots blower");
  });
});

describe("the build script's promises about library.html", () => {
  const html = readFileSync(LIBRARY_HTML, "utf8");

  it.each([
    ["cond", "Show sample condition"],
    ["spin", "Rotate shafts"],
    ["xray", "See inside"],
    ["flowb", "Show flow"],
    ["sensb", "Sensors"],
    ["dirb", "Rotation"],
    ["arrb", "arrows"],
    ["guard", "Show guards"],
    ["reset", "Reset view"],
    ["more", "Details"],
    ["png", "Save image"],
    ["glb", "Export 3D (GLB)"],
  ])("keeps the %s button (%s)", (elementId) => {
    expect(html).toContain(`id="${elementId}"`);
  });

  it("reaches no CDN", () => {
    // The viewer has to work on a plant network with no route out, and the
    // pinned three.js revision is what keeps the paint colours right.
    for (const host of [
      "cdnjs.cloudflare.com",
      "cdn.jsdelivr.net",
      "fonts.googleapis.com",
      "fonts.gstatic.com",
    ]) {
      expect(html, `${host} is still referenced`).not.toContain(host);
    }
  });

  it("loads three r128 and the exporter from vendor/", () => {
    expect(html).toContain("./vendor/three.r128.min.js");
    expect(html).toContain("./vendor/GLTFExporter.r128.js");
    expect(html).toContain("./vendor/barlow.css");
  });

  it("can save a file without the Claude downloads capability", () => {
    // The kit page ran as a Claude artifact. Left unpatched, `dl` stays null
    // and both export buttons hide themselves on load.
    expect(html).not.toContain("window.claude.use('downloads')");
    expect(html).toContain("URL.createObjectURL");
  });

  it("carries the host bridge", () => {
    expect(html).toContain("senvia-3d");
    expect(html).toContain("pointClick");
  });
});

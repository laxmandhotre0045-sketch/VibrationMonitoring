/**
 * The models and the adapter have to agree on every node name.
 *
 * This is the seam that fails silently. The viewer looks up a sensor by node
 * name; a miss is not an error, it is a marker that never appears — and with
 * twelve anchors on a model, one missing is easy to overlook until a plant
 * asks why their foundation probe is not on the picture.
 *
 * So this reads the real GLBs out of `public/models/`, and for every machine
 * type, every mounting location Step 5 offers and every orientation, checks the
 * name the adapter builds is a node the file actually contains.
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  bearingNodeName,
  glbUrlFor,
  proceduralModelIdFor,
  resolveMachineTypeId,
  sensorNodeName,
} from "../machine-type-map";
import { findProceduralModel } from "@/components/equipment/digital-twin/scene/procedural-source";
import type { MachineTypeId } from "../types";

const MODELS_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "..", "..", "..", "..",
  "public", "models"
);

/** Every Machine Type the Equipment Master offers in Step 1. */
const MACHINE_TYPES = [
  "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
  "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
  "Spindle", "Wind Turbine",
];

/** Every mounting location Step 5 offers, except the free-text escape hatch. */
const MOUNTING_LOCATIONS = [
  "Bearing Housing DE", "Bearing Housing NDE", "Motor DE", "Motor NDE",
  "Gearbox Input", "Gearbox Output", "Pump Casing", "Fan Housing",
  "Compressor Housing", "Foundation",
];

const ORIENTATIONS = ["Horizontal", "Vertical", "Axial"];

/** Node names out of a .glb — the JSON chunk is all this needs. */
function glbNodeNames(file: string): Set<string> {
  const buffer = readFileSync(file);
  // 12-byte header, then chunks of [length, type, data]. The first is JSON.
  const jsonLength = buffer.readUInt32LE(12);
  const json = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString("utf8"));
  return new Set<string>(
    (json.nodes ?? []).map((node: { name?: string }) => node.name ?? "").filter(Boolean)
  );
}

function modelFileFor(typeId: MachineTypeId): string | null {
  const url = glbUrlFor(typeId);
  if (!url) return null;
  const file = join(MODELS_DIR, url.replace("/models/", ""));
  return existsSync(file) ? file : null;
}

/** The registry anchor a mounting location resolves to for this family. */
function anchorIdFor(typeId: MachineTypeId, location: string): string {
  const model = findProceduralModel(proceduralModelIdFor(typeId));
  return model.mountingLocationMap[location] ?? model.fallbackAnchorId;
}

const TYPES_WITH_MODELS = [...new Set(MACHINE_TYPES.map(resolveMachineTypeId))].filter(
  (typeId) => modelFileFor(typeId) !== null
);

describe("the GLB library", () => {
  it("has a file for every family except the stand-in", () => {
    // Guards the guard: an empty list would make every test below vacuous.
    expect(TYPES_WITH_MODELS.length).toBeGreaterThanOrEqual(6);
    expect(TYPES_WITH_MODELS).not.toContain("generic");
  });

  it("routes every machine type to a family", () => {
    for (const machineType of MACHINE_TYPES) {
      const typeId = resolveMachineTypeId(machineType);
      // "generic" is the honest answer for a type with no model; what would be
      // wrong is a type silently falling through to it once one exists.
      expect(typeId, `${machineType} has no family`).toBeTruthy();
    }
    expect(resolveMachineTypeId("Spindle")).toBe("spindle");
    expect(resolveMachineTypeId("Wind Turbine")).toBe("wind-turbine");
    expect(resolveMachineTypeId("Conveyor")).toBe("conveyor");
    expect(resolveMachineTypeId("Generator")).toBe("generator");
    expect(resolveMachineTypeId("Mixer")).toBe("mixer");
    expect(resolveMachineTypeId("Nothing Like This")).toBe("generic");
  });
});

describe.each(TYPES_WITH_MODELS)("%s.glb", (typeId) => {
  const names = glbNodeNames(modelFileFor(typeId) as string);

  it("carries the nodes the contract requires", () => {
    expect(names.has("ROTOR"), "no ROTOR node").toBe(true);
    expect([...names].some((n) => n.startsWith("BRG_")), "no bearing anchors").toBe(true);
    expect([...names].some((n) => n.startsWith("SNS_")), "no sensor anchors").toBe(true);
    expect([...names].some((n) => n.startsWith("CASING")), "no x-ray layer").toBe(true);
  });

  it.each(MOUNTING_LOCATIONS)("places a sensor mounted on %s", (location) => {
    const anchorId = anchorIdFor(typeId, location);
    for (const orientation of ORIENTATIONS) {
      const node = sensorNodeName(anchorId, orientation, typeId);
      expect(names.has(node), `${typeId}: ${location} ${orientation} -> ${node}`).toBe(
        true
      );
    }
  });

  it("places every bearing the model draws", () => {
    // Ghost bearings are built from the registry's anchor list, so each one
    // has to resolve too — otherwise the twin shows a chip with no marker.
    const model = findProceduralModel(proceduralModelIdFor(typeId));
    for (const anchor of model.bearingAnchors) {
      const node = bearingNodeName(anchor.id, typeId);
      expect(names.has(node), `${typeId}: ${anchor.id} -> ${node}`).toBe(true);
    }
  });
});

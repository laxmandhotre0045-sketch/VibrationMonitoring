/**
 * Every machine has something that turns.
 *
 * "Run shaft" spins the ROTOR group, and the viewer builds that group by
 * *inference*: a component joins it when its tone is "shaft" and it sits on the
 * model centre line. Nothing fails when a model has no such component — the
 * toggle simply does nothing, on a page where nothing else is moving either, so
 * it reads as a broken button rather than a machine with no shaft.
 *
 * These build each procedural model for real and look at what ended up in the
 * rotor.
 */
import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { MACHINE_MODELS } from "@/lib/digital-twin/machine-registry";
import { buildProceduralSource } from "../scene/procedural-source";

/** Every model id the registry can be asked for. */
const MODEL_IDS = MACHINE_MODELS.map((model) => model.id);

function rotorParts(modelId: string): THREE.Object3D[] {
  const source = buildProceduralSource(modelId);
  return source.rotor ? [...source.rotor.children] : [];
}

describe("the rotor", () => {
  it("covers every model the registry publishes", () => {
    // Guards the guard: if the registry were renamed or emptied, the per-model
    // assertions below would silently test nothing.
    expect(MODEL_IDS.length).toBeGreaterThanOrEqual(5);
  });

  it.each(MODEL_IDS)("%s has at least one turning part", (modelId) => {
    expect(rotorParts(modelId).length).toBeGreaterThan(0);
  });

  it.each(MODEL_IDS)("%s turns its shafts about their own centres", (modelId) => {
    // ROTOR spins on `rotation.x` through the group origin, so a part sitting
    // at an offset orbits the centre line rather than turning in place. That is
    // right for impeller blades, which are arranged at a radius and are meant
    // to sweep a circle. It is wrong for a shaft, which has a centre of its own
    // — that one goes in `extraRotors` with a pivot instead.
    for (const part of rotorParts(modelId)) {
      if (!part.name.includes("shaft")) continue;
      const offset = Math.hypot(part.position.y, part.position.z);
      expect(offset, `${modelId}: ${part.name} would orbit, not turn`).toBeLessThan(0.05);
    }
  });

  it("gives an off-centre shaft a pivot of its own", () => {
    // The gearbox output sits on a second centre line. In ROTOR it swung
    // around the input instead of turning.
    const source = buildProceduralSource("gearbox");
    const extra = source.extraRotors ?? [];

    expect(extra.length).toBeGreaterThan(0);
    for (const pivot of extra) {
      // The pivot carries the offset; the mesh inside sits on its axis.
      expect(Math.hypot(pivot.position.y, pivot.position.z)).toBeGreaterThan(0.05);
      for (const child of pivot.children) {
        expect(Math.hypot(child.position.y, child.position.z)).toBeLessThan(0.05);
      }
    }
  });

  it("spins the shaft the motor actually drives", () => {
    const names = rotorParts("motor").map((part) => part.name);
    expect(names.some((name) => name.includes("shaft"))).toBe(true);
  });

  it.each(["pump", "compressor"])("%s has a driven shaft of its own", (modelId) => {
    // Both are driven machines: a motor shaft, a coupling, and a shaft carrying
    // the impeller or the crank. Without the driven half the twin shows a
    // motor turning next to a casing that never moves.
    const names = rotorParts(modelId).map((part) => part.name);
    expect(names.filter((name) => name.includes("shaft")).length).toBeGreaterThanOrEqual(2);
  });
});

/**
 * Digital Twin — machine type resolution and the anchor naming contract.
 *
 * Two jobs:
 *
 *   1. Map the thirteen `machine_type` values Step 1 offers onto the seven
 *      model families the viewer draws, and to their asset URLs.
 *   2. Own the canonical anchor node names. This is the contract the 3D artist
 *      builds to (see `docs/digital-twin-models.md`) *and* the names the
 *      procedural builder synthesises, which is what lets one viewer consume
 *      either source without caring which it got.
 */

import type { MachineTypeId, SensorOrientation } from "./types";

/** `machine_type` → model family. Everything unlisted falls to "generic". */
const TYPE_BY_MACHINE: Record<string, MachineTypeId> = {
  motor: "motor",
  generator: "motor",
  "dg set": "motor",
  turbine: "motor",
  pump: "pump",
  fan: "fan",
  blower: "blower",
  compressor: "compressor",
  gearbox: "gearbox",
};

/**
 * Which registry model draws a family when no GLB is available.
 *
 * A blower is a fan with a different casing, so it shares the fan's procedural
 * geometry while still loading its own `blower.glb` when one exists.
 */
const PROCEDURAL_MODEL_BY_TYPE: Record<MachineTypeId, string> = {
  motor: "motor",
  pump: "pump",
  fan: "fan",
  blower: "fan",
  compressor: "compressor",
  gearbox: "gearbox",
  generic: "generic",
};

export function resolveMachineTypeId(machineType: string | null | undefined): MachineTypeId {
  const key = (machineType ?? "").trim().toLowerCase();
  return TYPE_BY_MACHINE[key] ?? "generic";
}

export function proceduralModelIdFor(typeId: MachineTypeId): string {
  return PROCEDURAL_MODEL_BY_TYPE[typeId];
}

/**
 * Where the GLB for a family lives.
 *
 * "generic" has no GLB by design — it is the stand-in for machine types that
 * do not have a model of their own.
 */
export function glbUrlFor(typeId: MachineTypeId): string | null {
  return typeId === "generic" ? null : `/models/${typeId}.glb`;
}

/** The static image shown while the model loads. */
export function previewUrlFor(typeId: MachineTypeId): string {
  return `/models/previews/${typeId}.png`;
}

// ---------------------------------------------------------------------------
// Anchor naming contract
// ---------------------------------------------------------------------------

/** Single-letter axis suffix used in anchor node names. */
const AXIS_SUFFIX: Record<string, string> = {
  horizontal: "H",
  vertical: "V",
  axial: "A",
  radial: "R",
  tangential: "T",
};

export function axisSuffix(orientation: string | null | undefined): string {
  return AXIS_SUFFIX[(orientation ?? "").trim().toLowerCase()] ?? "H";
}

export function axisFromSuffix(suffix: string): SensorOrientation {
  const found = Object.entries(AXIS_SUFFIX).find(
    ([, value]) => value === suffix.trim().toUpperCase()
  );
  if (!found) return "Horizontal";
  const word = found[0];
  return (word.charAt(0).toUpperCase() + word.slice(1)) as SensorOrientation;
}

/**
 * Registry anchor id → node-name slug: `motor.de` becomes `MOTOR_DE`.
 *
 * Node names are the artist-facing contract, so they are upper snake case
 * rather than the dotted ids used internally.
 */
export function anchorSlug(anchorId: string): string {
  return anchorId.trim().toUpperCase().replace(/[.\s-]+/g, "_");
}

/** `BRG_MOTOR_DE` — the node a bearing sits on. */
export function bearingNodeName(anchorId: string): string {
  return `BRG_${anchorSlug(anchorId)}`;
}

/**
 * `CH_MOTOR_DE_H` — the node a sensor sits on.
 *
 * Keyed by mounting location and axis rather than by channel number: channel
 * numbers here are positional (there is no channel column in the database), so
 * deleting one sensor would otherwise re-point every marker after it.
 */
export function sensorNodeName(anchorId: string, orientation: string | null | undefined): string {
  return `CH_${anchorSlug(anchorId)}_${axisSuffix(orientation)}`;
}

/** True for a node name the x-ray layer or anchor scan should pick up. */
export const XRAY_NAME_PATTERN = /casing|housing|cover|guard/i;
export const SENSOR_NODE_PATTERN = /^CH[\W_]?\d+$|^CH_/i;
export const BEARING_NODE_PATTERN = /^BRG[\W_]/i;
export const ROTOR_NODE_PATTERN = /^ROTOR$/i;

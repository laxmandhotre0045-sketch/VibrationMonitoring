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
  pump: "pump",
  fan: "fan",
  blower: "blower",
  compressor: "compressor",
  gearbox: "gearbox",
  turbine: "turbine",
  "dg set": "dg-set",
  spindle: "spindle",
  "wind turbine": "wind-turbine",
  generator: "generator",
  conveyor: "conveyor",
  crusher: "crusher",
  mixer: "mixer",
  agitator: "agitator",
};

/**
 * File name per family, where it differs from the id.
 *
 * Only the drivetrain does: the id says what the asset is, the file says what
 * the artist delivered.
 */
const GLB_FILE: Partial<Record<MachineTypeId, string>> = {
  "wind-turbine": "wind-turbine-drivetrain",
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
  // The five families added with the GLB library have no procedural twin of
  // their own. They fall back to the closest one that exists, so a missing or
  // failed GLB still draws a machine of roughly the right shape.
  turbine: "motor",
  "dg-set": "motor",
  generator: "motor",
  "machine-train": "generic",
  spindle: "generic",
  "wind-turbine": "generic",
  conveyor: "generic",
  crusher: "generic",
  mixer: "generic",
  agitator: "generic",
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
  if (typeId === "generic") return null;
  return `/models/${GLB_FILE[typeId] ?? typeId}.glb`;
}

/**
 * Which family's still stands in while a model loads.
 *
 * Previews are rendered from the procedural registry, which covers six
 * families. A GLB-only family borrows the still of the procedural model it
 * falls back to — the wrong machine for a moment beats an empty stage.
 */
const PREVIEW_FILE: Record<MachineTypeId, string> = {
  motor: "motor",
  pump: "pump",
  fan: "fan",
  blower: "blower",
  compressor: "compressor",
  gearbox: "gearbox",
  turbine: "motor",
  "dg-set": "motor",
  generator: "motor",
  "machine-train": "generic",
  spindle: "generic",
  "wind-turbine": "generic",
  conveyor: "generic",
  crusher: "generic",
  mixer: "generic",
  agitator: "generic",
  generic: "generic",
};

/** The static image shown while the model loads. */
export function previewUrlFor(typeId: MachineTypeId): string {
  return `/models/previews/${PREVIEW_FILE[typeId] ?? "generic"}.png`;
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

/**
 * Registry anchor id → the location token a model actually uses, per family.
 *
 * The procedural registry and the GLB library grew up separately and name some
 * of the same places differently: the registry calls a compressor bearing
 * `compressor.de`, the model calls it `COMP_DE`. Rather than rename one side —
 * the registry ids are load-bearing for geometry, the model names are the
 * artist's contract — the difference lives here, as data.
 *
 * Adding a machine type is an edit to this table and the two above it. No new
 * code, which is the whole point of keeping it in one place.
 */
const LOCATION_ALIAS: Partial<Record<MachineTypeId, Record<string, string>>> = {
  compressor: {
    COMPRESSOR_DE: "COMP_DE",
    COMPRESSOR_NDE: "COMP_NDE",
    COMPRESSOR_CASING: "COMP_HOUSING",
  },
  // A blower borrows the fan's procedural geometry, so its anchors arrive
  // named after a fan. The model is its own machine and says so.
  blower: {
    FAN_DE: "BLOWER_DE",
    FAN_NDE: "BLOWER_NDE",
    FAN_HOUSING: "BLOWER_HOUSING",
  },
  // The model has both shafts; the procedural stand-in has one. Input and
  // output land on the high- and low-speed shafts, and a sensor recorded
  // against the motor lands on the high-speed shaft it drives.
  gearbox: {
    GEARBOX_INPUT: "GB_HSS_DE",
    GEARBOX_OUTPUT: "GB_LSS_DE",
    MOTOR_DE: "GB_HSS_DE",
    MOTOR_NDE: "GB_HSS_NDE",
  },
  // These four fall back to the motor or generic procedural model, so their
  // anchors arrive named MOTOR_* or GENERIC_* whichever machine they really
  // are. The alias is what turns that back into the model's own vocabulary.
  turbine: { MOTOR_DE: "TURB_DE", MOTOR_NDE: "TURB_NDE" },
  "dg-set": { MOTOR_DE: "ALT_DE", MOTOR_NDE: "ALT_NDE" },
  spindle: { GENERIC_DE: "SPINDLE_FRONT", GENERIC_NDE: "SPINDLE_REAR" },
  "wind-turbine": { GENERIC_DE: "GEN_DE", GENERIC_NDE: "GEN_NDE" },
  "machine-train": { GENERIC_DE: "DRIVEN_DE", GENERIC_NDE: "DRIVEN_NDE" },
  generator: { MOTOR_DE: "GEN_DE", MOTOR_NDE: "GEN_NDE" },
  conveyor: { GENERIC_DE: "PULLEY_DE", GENERIC_NDE: "PULLEY_NDE" },
  crusher: { GENERIC_DE: "CRSH_DE", GENERIC_NDE: "CRSH_NDE" },
  mixer: { GENERIC_DE: "MIX_DE", GENERIC_NDE: "MIX_NDE" },
  agitator: { GENERIC_DE: "MIX_DE", GENERIC_NDE: "MIX_NDE" },
};

/** The token this family uses for a registry anchor. */
export function locationToken(anchorId: string, typeId?: MachineTypeId): string {
  const slug = anchorSlug(anchorId);
  if (!typeId) return slug;
  return LOCATION_ALIAS[typeId]?.[slug] ?? slug;
}

/** `BRG_MOTOR_DE` — the node a bearing sits on. */
export function bearingNodeName(anchorId: string, typeId?: MachineTypeId): string {
  return `BRG_${locationToken(anchorId, typeId)}`;
}

/**
 * `CH_MOTOR_DE_H` — the node a sensor sits on.
 *
 * Keyed by mounting location and axis rather than by channel number: channel
 * numbers here are positional (there is no channel column in the database), so
 * deleting one sensor would otherwise re-point every marker after it.
 */
export function sensorNodeName(
  anchorId: string,
  orientation: string | null | undefined,
  typeId?: MachineTypeId
): string {
  return `SNS_${locationToken(anchorId, typeId)}_${axisSuffix(orientation)}`;
}

/** True for a node name the x-ray layer or anchor scan should pick up. */
export const XRAY_NAME_PATTERN = /casing|housing|cover|guard/i;
/**
 * `SNS_` is the contract in docs/digital-twin-models.md and what every model in
 * `public/models/` uses. `CH_` is the name the procedural builder emitted
 * before the GLB library landed, kept so a model authored against the older
 * draft still loads instead of silently showing no sensors at all.
 */
export const SENSOR_NODE_PATTERN = /^SNS_|^CH[\W_]?\d+$|^CH_/i;
export const BEARING_NODE_PATTERN = /^BRG[\W_]/i;
export const ROTOR_NODE_PATTERN = /^ROTOR$/i;

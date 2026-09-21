/**
 * Digital Twin — geometry vocabulary.
 *
 * A machine model is described declaratively here and turned into three.js
 * objects by `twin-scene.ts`. Nothing in this file imports three, so the
 * registry stays cheap to load and easy to test.
 *
 * Coordinate system (shared by every model):
 *
 *   +X  along the shaft, pointing from the non-drive end toward the drive end
 *   +Y  up
 *   +Z  horizontal, across the shaft
 *
 * That is the same frame vibration analysts use, which is what lets an
 * orientation be turned into a direction instead of being drawn by hand:
 * Axial is the shaft axis, Vertical is up, Horizontal is across.
 *
 * One unit is roughly 100 mm. The models are schematic, not scale drawings of
 * any manufacturer's part.
 */

export type Vec3 = [number, number, number];

/** Which primitive draws a component, and how its size is read. */
export type ComponentShape =
  /** size = [length(X), height(Y), depth(Z)] */
  | "box"
  /** size = [radius, length, radius] — length runs along `axis` */
  | "cylinder"
  /** size = [radiusTop, length, radiusBottom] — length runs along `axis` */
  | "cone";

/** Surface treatment. Resolved to real colours in `twin-scene.ts`. */
export type ComponentTone = "body" | "casing" | "shaft" | "base" | "guard";

export interface MachineComponentSpec {
  id: string;
  /** Shown when the component is clicked. */
  label: string;
  shape: ComponentShape;
  /** Centre of the primitive. */
  position: Vec3;
  size: Vec3;
  /** Axis a cylinder/cone runs along. Ignored by `box`. Default "x". */
  axis?: "x" | "y" | "z";
  /** Extra euler rotation (radians, XYZ) applied after `axis` — radial fins. */
  rotation?: Vec3;
  tone?: ComponentTone;
  /**
   * Part of the rotating assembly: goes into the ROTOR group and turns with
   * "Run shaft". Without it, only centre-line shafts are inferred to spin.
   */
  spin?: boolean;
  /**
   * Force this part in or out of the x-ray layer, overriding the tone default.
   * An impeller inside a scroll should stay solid; a plinth never fades.
   */
  xray?: boolean;
}

/**
 * A place a bearing physically sits: a ring concentric with the shaft.
 *
 * Bearings are only ever drawn at one of these, so a configured bearing can
 * never end up floating somewhere arbitrary.
 */
export interface BearingAnchorSpec {
  id: string;
  /** "Motor DE", "Pump NDE", "Gearbox Input" … */
  label: string;
  /** Centre of the ring — sits on the shaft axis. */
  position: Vec3;
  /** Outer radius of the bearing ring. */
  radius: number;
}

/**
 * A place a sensor can be stud-mounted.
 *
 * The anchor records the *geometry* of the mounting point, not one point per
 * orientation: the orientation supplies the direction, and the marker is
 * pushed out along it to the machine surface. A vertical sensor therefore ends
 * up on top of the housing and an axial one on its end face, from a single
 * anchor definition.
 */
export interface SensorAnchorSpec {
  id: string;
  /** "Motor DE", "Pump Casing" … */
  label: string;
  /** Point on the rotating axis this mounting point straddles. */
  axisPoint: Vec3;
  /** Distance from that axis out to the mounting surface. */
  radius: number;
  /** X of the end face an axial sensor mounts on. */
  axialFace: number;
  /** Which way that face looks: +1 toward +X, -1 toward -X. */
  axialSign: 1 | -1;
  /**
   * True for mounting points with no rotating axis of their own (Foundation).
   * Radial and Tangential have no meaning there and fall back to Vertical.
   */
  static?: boolean;
}

export interface MachineModelSpec {
  id: string;
  label: string;
  /**
   * `machine_type` values that resolve to this model, matched
   * case-insensitively. Taken from the Machine Type list in Step 1.
   */
  matches: string[];
  components: MachineComponentSpec[];
  bearingAnchors: BearingAnchorSpec[];
  sensorAnchors: SensorAnchorSpec[];
  /** Where `bearing_number_de` is drawn on this model. */
  deBearingAnchorId: string;
  /** Where `bearing_number_nde` is drawn on this model. */
  ndeBearingAnchorId: string;
  /** Step 5 mounting location → sensor anchor id. */
  mountingLocationMap: Record<string, string>;
  /**
   * Anchor for a mounting location this model has no equivalent for. The
   * marker is flagged `mapped: false` so the UI can say so rather than imply
   * the machine has a part it does not.
   */
  fallbackAnchorId: string;
  /**
   * True for the generic stand-in used by machine types without a dedicated
   * model. Surfaced in the UI so it never reads as a real model of the asset.
   */
  schematic?: boolean;
}

/** The five orientations offered in Step 5. */
export type SensorOrientation =
  | "Horizontal"
  | "Vertical"
  | "Axial"
  | "Radial"
  | "Tangential";

/** A bearing resolved onto an anchor, ready to draw. */
export interface ResolvedBearing {
  /** Stable key — also the pick id on the three.js object. */
  key: string;
  /** "DE" | "NDE" */
  position: "DE" | "NDE";
  anchor: BearingAnchorSpec;
  /** Free-text bearing number from the form. */
  bearingNumber: string;
  /** Catalogue id when the bearing was matched against the fault-frequency table. */
  catalogId: number | null;
}

/** A sensor resolved onto an anchor, ready to draw. */
export interface ResolvedSensor {
  key: string;
  /** Display channel label, derived by position: CH1, CH2 … */
  channel: string;
  /** Row label for the six standard mounting points; blank for added sensors. */
  rowLabel: string;
  mountingLocation: string;
  orientation: string;
  /** Present only for rows from the Additional Sensors list. */
  sensorType: string | null;
  /**
   * "mounting" — one of the six standard Sensor Mounting & Orientation rows.
   * "sensor"   — a record from Additional Sensors, saved with the equipment.
   */
  source: "mounting" | "sensor";
  anchor: SensorAnchorSpec;
  /** False when the mounting location has no equivalent part on this model. */
  mapped: boolean;
  /** Where the marker sits. */
  markerPosition: Vec3;
  /** Unit vector the orientation arrow points along. */
  direction: Vec3;
}

/** Everything the viewer draws, for one equipment configuration. */
export interface ResolvedTwin {
  model: MachineModelSpec;
  machineType: string;
  machineName: string;
  bearings: ResolvedBearing[];
  /**
   * Bearing positions this model has that the form has *not* filled in.
   *
   * Drawn as a faint outline so the operator can see where a bearing would go,
   * without the twin claiming one is fitted. Bearing details are optional in
   * Step 3 and stay that way.
   */
  ghostBearingAnchors: BearingAnchorSpec[];
  sensors: ResolvedSensor[];
}

/** What a click in the 3D scene resolves to. */
export type TwinPick =
  | { kind: "bearing"; key: string }
  | { kind: "sensor"; key: string };

// ---------------------------------------------------------------------------
// Viewer public API
//
// The shapes `<DigitalTwinViewer>` takes. Deliberately independent of
// `EquipmentFormData`: one adapter turns the saved equipment record into these,
// and everything downstream — GLB path and procedural path alike — speaks only
// this vocabulary.
// ---------------------------------------------------------------------------

/** The model families the viewer can draw. */
export type MachineTypeId =
  | "fan"
  | "pump"
  | "blower"
  | "motor"
  | "gearbox"
  | "compressor"
  | "generic";

/** Optional condition colouring. Not sent by the setup flow yet. */
export type SensorStatus = "ok" | "alert" | "danger";

/**
 * A bearing to draw.
 *
 * `configured` false means the machine has this bearing position but the form
 * has not filled it in — drawn as a faint outline, never as a fitted part.
 */
export interface TwinBearing {
  id: string;
  /** Short chip text, e.g. "Fan DE". */
  name: string;
  /** Secondary line in the detail card, e.g. the part number. */
  note?: string;
  configured: boolean;
  /** Name of the `BRG_*` node this sits on. */
  anchorNode: string;
}

/** A sensor to draw. */
export interface TwinSensor {
  id: string;
  axis: SensorOrientation;
  /** Mounting location as the form records it, e.g. "Motor DE". */
  location: string;
  /** Name of the `CH*` node this sits on. */
  anchorNode: string;
  status?: SensorStatus;
  /** Sensor type, when this came from an Additional Sensors record. */
  detail?: string;
  /**
   * False for the six standard mounting rows, which are reference points
   * rather than saved sensor records.
   */
  persisted?: boolean;
}

/**
 * A model the viewer can render, however it was produced.
 *
 * Both `loadGlbSource` and `buildProceduralSource` return this, which is what
 * lets the viewer stay ignorant of where the geometry came from.
 */
export interface TwinModelSource {
  /** Everything to add to the scene. */
  root: import("three").Object3D;
  /** `CH*` mounting empties, by node name. Local +Y is the measurement axis. */
  sensorAnchors: Map<string, import("three").Object3D>;
  /** `BRG_*` empties, by node name. */
  bearingAnchors: Map<string, import("three").Object3D>;
  /** Casing / housing / cover / guard meshes — the x-ray layer. */
  xrayMeshes: import("three").Mesh[];
  /** The group holding everything that spins, if the model has one. */
  rotor: import("three").Object3D | null;
  /** "glb" | "procedural" — surfaced in the UI so a stand-in reads as one. */
  kind: "glb" | "procedural";
  /** True when this is the generic stand-in rather than a model of this type. */
  schematic: boolean;
}

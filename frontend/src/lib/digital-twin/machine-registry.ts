/**
 * Digital Twin — machine model registry.
 *
 * One entry per machine topology, keyed to the `machine_type` values offered in
 * Step 1 of Equipment Master. Adding a machine type means adding a spec here;
 * the viewer, the anchors and the sensor/bearing placement all read from this
 * file and need no changes.
 *
 * The models are deliberately schematic: they show the parts a vibration
 * analyst mounts sensors on — body, shaft, bearing housings, casing — at
 * roughly the right proportions. They are not scale models of any
 * manufacturer's equipment, and the UI says so.
 *
 * See `types.ts` for the coordinate frame.
 */

import { DETAILED_FAN_MODEL } from "./procedural-fan";
import type {
  BearingAnchorSpec,
  MachineComponentSpec,
  MachineModelSpec,
  SensorAnchorSpec,
  Vec3,
} from "./types";

/** Shaft centre height for every model, so cameras and anchors agree. */
const AXIS_Y = 0;
/** Top face of the base plate. Feet bridge from a body down to here. */
const BASE_TOP = -1.45;

/** The Foundation mounting point — every model has one. */
function foundationAnchor(centreX: number, farX: number): SensorAnchorSpec {
  return {
    id: "foundation",
    label: "Foundation",
    axisPoint: [centreX, BASE_TOP, 0],
    radius: 0.35,
    axialFace: farX,
    axialSign: 1,
    static: true,
  };
}

function basePlate(centreX: number, length: number, depth = 2.8): MachineComponentSpec {
  return {
    id: "base",
    label: "Base / Skid",
    shape: "box",
    position: [centreX, BASE_TOP - 0.15, 0],
    size: [length, 0.3, depth],
    tone: "base",
  };
}

interface SubAssembly {
  components: MachineComponentSpec[];
  bearingAnchors: BearingAnchorSpec[];
  sensorAnchors: SensorAnchorSpec[];
}

/**
 * The driving motor used by the pump, fan, compressor and gearbox models.
 *
 * `deX` is where the motor's drive end face sits; the body runs back from
 * there toward -X, so the driven machine can be laid out from `deX` forward.
 */
function drivingMotor(deX: number, bodyLength = 2.8, radius = 0.95): SubAssembly {
  const bellR = radius * 0.84;
  const bodyEndX = deX - 0.3;
  const bodyStartX = bodyEndX - bodyLength;
  const bodyCentreX = (bodyStartX + bodyEndX) / 2;
  const ndeX = bodyStartX - 0.3;

  return {
    components: [
      {
        id: "motor.body",
        label: "Motor Body",
        shape: "cylinder",
        position: [bodyCentreX, AXIS_Y, 0],
        size: [radius, bodyLength, radius],
        tone: "body",
      },
      {
        id: "motor.bell.de",
        label: "Motor DE End Bell",
        shape: "cylinder",
        position: [deX - 0.15, AXIS_Y, 0],
        size: [bellR, 0.3, bellR],
        tone: "casing",
      },
      {
        id: "motor.bell.nde",
        label: "Motor NDE End Bell",
        shape: "cylinder",
        position: [ndeX + 0.15, AXIS_Y, 0],
        size: [bellR, 0.3, bellR],
        tone: "casing",
      },
      {
        id: "motor.terminal",
        label: "Terminal Box",
        shape: "box",
        position: [bodyCentreX, radius + 0.22, 0],
        size: [bodyLength * 0.4, 0.45, radius * 0.95],
        tone: "casing",
      },
      {
        id: "motor.feet",
        label: "Motor Feet",
        shape: "box",
        position: [bodyCentreX, (BASE_TOP - radius) / 2, 0],
        size: [bodyLength * 0.9, -BASE_TOP - radius, radius * 2.1],
        tone: "base",
      },
    ],
    bearingAnchors: [
      {
        id: "motor.de",
        label: "Motor DE",
        position: [deX - 0.05, AXIS_Y, 0],
        radius: radius * 0.5,
      },
      {
        id: "motor.nde",
        label: "Motor NDE",
        position: [ndeX + 0.05, AXIS_Y, 0],
        radius: radius * 0.5,
      },
    ],
    sensorAnchors: [
      {
        id: "motor.de",
        label: "Motor DE",
        axisPoint: [deX - 0.15, AXIS_Y, 0],
        radius: bellR,
        axialFace: deX,
        axialSign: 1,
      },
      {
        id: "motor.nde",
        label: "Motor NDE",
        axisPoint: [ndeX + 0.15, AXIS_Y, 0],
        radius: bellR,
        axialFace: ndeX,
        axialSign: -1,
      },
    ],
  };
}

/** Coupling between a motor DE and a driven shaft. */
function coupling(centreX: number, radius = 0.42): MachineComponentSpec[] {
  return [
    {
      id: "shaft.drive",
      label: "Drive Shaft",
      shape: "cylinder",
      position: [centreX, AXIS_Y, 0],
      size: [radius * 0.4, radius * 4.4, radius * 0.4],
      tone: "shaft",
    },
    {
      id: "coupling",
      label: "Coupling",
      shape: "cylinder",
      position: [centreX, AXIS_Y, 0],
      size: [radius, radius * 1.6, radius],
      tone: "guard",
    },
  ];
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

/**
 * Standalone rotating machine: body between two bearings.
 *
 * Covers the machine types whose whole asset *is* the motor/generator — the
 * form's DE and NDE are that machine's own two bearings.
 */
const MOTOR_MODEL: MachineModelSpec = (() => {
  const radius = 1.1;
  const bodyLength = 3.4;
  const deX = 2.0;
  const ndeX = -2.0;

  return {
    id: "motor",
    label: "Electric Motor",
    matches: ["Motor", "Generator", "DG Set", "Turbine"],
    components: [
      basePlate(0, 6.4),
      {
        id: "motor.body",
        label: "Motor Body",
        shape: "cylinder",
        position: [0, AXIS_Y, 0],
        size: [radius, bodyLength, radius],
        tone: "body",
      },
      {
        id: "motor.bell.de",
        label: "DE End Bell",
        shape: "cylinder",
        position: [deX - 0.15, AXIS_Y, 0],
        size: [radius * 0.85, 0.3, radius * 0.85],
        tone: "casing",
      },
      {
        id: "motor.bell.nde",
        label: "NDE End Bell",
        shape: "cylinder",
        position: [ndeX + 0.15, AXIS_Y, 0],
        size: [radius * 0.85, 0.3, radius * 0.85],
        tone: "casing",
      },
      {
        id: "motor.shaft",
        label: "Shaft",
        shape: "cylinder",
        position: [deX + 0.7, AXIS_Y, 0],
        size: [0.22, 1.6, 0.22],
        tone: "shaft",
      },
      {
        id: "motor.terminal",
        label: "Terminal Box",
        shape: "box",
        position: [0, radius + 0.24, 0],
        size: [1.4, 0.48, 1.0],
        tone: "casing",
      },
      {
        id: "motor.fan.cowl",
        label: "Cooling Fan Cowl",
        shape: "cylinder",
        position: [ndeX - 0.35, AXIS_Y, 0],
        size: [radius * 0.7, 0.5, radius * 0.7],
        tone: "guard",
      },
      {
        id: "motor.feet",
        label: "Motor Feet",
        shape: "box",
        position: [0, (BASE_TOP - radius) / 2, 0],
        size: [bodyLength * 0.92, -BASE_TOP - radius, radius * 2.2],
        tone: "base",
      },
    ],
    bearingAnchors: [
      { id: "motor.de", label: "Motor DE", position: [deX - 0.05, AXIS_Y, 0], radius: 0.56 },
      { id: "motor.nde", label: "Motor NDE", position: [ndeX + 0.05, AXIS_Y, 0], radius: 0.56 },
    ],
    sensorAnchors: [
      {
        id: "motor.de",
        label: "Motor DE",
        axisPoint: [deX - 0.15, AXIS_Y, 0],
        radius: radius * 0.85,
        axialFace: deX,
        axialSign: 1,
      },
      {
        id: "motor.nde",
        label: "Motor NDE",
        axisPoint: [ndeX + 0.15, AXIS_Y, 0],
        radius: radius * 0.85,
        axialFace: ndeX,
        axialSign: -1,
      },
      foundationAnchor(0, 3.2),
    ],
    deBearingAnchorId: "motor.de",
    ndeBearingAnchorId: "motor.nde",
    mountingLocationMap: {
      "Motor DE": "motor.de",
      "Motor NDE": "motor.nde",
      "Bearing Housing DE": "motor.de",
      "Bearing Housing NDE": "motor.nde",
      Foundation: "foundation",
    },
    fallbackAnchorId: "foundation",
  };
})();

/** Motor → coupling → centrifugal pump. */
const PUMP_MODEL: MachineModelSpec = (() => {
  const motor = drivingMotor(-2.1);
  const pumpDeX = -0.85;
  const pumpNdeX = 0.55;
  const casingX = 1.7;

  return {
    id: "pump",
    label: "Centrifugal Pump Set",
    matches: ["Pump"],
    components: [
      basePlate(-1.2, 9.2, 2.9),
      ...motor.components,
      ...coupling(-1.45, 0.42),
      {
        id: "pump.bearing.housing",
        label: "Pump Bearing Housing",
        shape: "cylinder",
        position: [-0.15, AXIS_Y, 0],
        size: [0.6, 1.9, 0.6],
        tone: "casing",
      },
      {
        id: "pump.pedestal",
        label: "Pump Pedestal",
        shape: "box",
        position: [-0.15, (BASE_TOP - 0.6) / 2, 0],
        size: [1.6, -BASE_TOP - 0.6, 1.3],
        tone: "base",
      },
      {
        // Kept a little smaller than the motor body: on a real pump set the
        // motor is the bigger volume, and an oversized volute swallows the
        // bearing housing the DE/NDE sensors mount on.
        id: "pump.casing",
        label: "Pump Casing (Volute)",
        shape: "cylinder",
        position: [casingX, AXIS_Y, 0],
        size: [1.0, 0.9, 1.0],
        tone: "casing",
      },
      {
        id: "pump.suction",
        label: "Suction Nozzle",
        shape: "cylinder",
        position: [casingX + 0.8, AXIS_Y, 0],
        size: [0.42, 0.75, 0.42],
        tone: "guard",
      },
      {
        id: "pump.discharge",
        label: "Discharge Nozzle",
        shape: "cylinder",
        position: [casingX, 1.4, 0],
        size: [0.34, 1.0, 0.34],
        axis: "y",
        tone: "guard",
      },
    ],
    bearingAnchors: [
      ...motor.bearingAnchors,
      { id: "pump.de", label: "Pump DE", position: [pumpDeX, AXIS_Y, 0], radius: 0.44 },
      { id: "pump.nde", label: "Pump NDE", position: [pumpNdeX, AXIS_Y, 0], radius: 0.44 },
    ],
    sensorAnchors: [
      ...motor.sensorAnchors,
      {
        id: "pump.de",
        label: "Pump DE (Bearing Housing)",
        axisPoint: [pumpDeX, AXIS_Y, 0],
        radius: 0.6,
        axialFace: -1.1,
        axialSign: -1,
      },
      {
        id: "pump.nde",
        label: "Pump NDE (Bearing Housing)",
        axisPoint: [pumpNdeX, AXIS_Y, 0],
        radius: 0.6,
        axialFace: 0.8,
        axialSign: 1,
      },
      {
        id: "pump.casing",
        label: "Pump Casing",
        axisPoint: [casingX, AXIS_Y, 0],
        radius: 1.0,
        axialFace: casingX + 0.45,
        axialSign: 1,
      },
      foundationAnchor(-1.2, 3.2),
    ],
    deBearingAnchorId: "pump.de",
    ndeBearingAnchorId: "pump.nde",
    mountingLocationMap: {
      "Motor DE": "motor.de",
      "Motor NDE": "motor.nde",
      "Bearing Housing DE": "pump.de",
      "Bearing Housing NDE": "pump.nde",
      "Pump Casing": "pump.casing",
      Foundation: "foundation",
    },
    fallbackAnchorId: "foundation",
  };
})();

/** Motor → coupling → compressor block. */
const COMPRESSOR_MODEL: MachineModelSpec = (() => {
  const motor = drivingMotor(-2.2, 2.8, 0.95);
  const compDeX = -0.9;
  const compNdeX = 1.6;
  const casingX = 0.5;

  return {
    id: "compressor",
    label: "Compressor Set",
    matches: ["Compressor"],
    components: [
      basePlate(-1.4, 9.6, 3.0),
      ...motor.components,
      ...coupling(-1.55, 0.42),
      {
        id: "compressor.casing",
        label: "Compressor Casing",
        shape: "box",
        position: [casingX, 0.1, 0],
        size: [2.6, 2.1, 1.9],
        tone: "casing",
      },
      {
        id: "compressor.head",
        label: "Cylinder Head",
        shape: "cylinder",
        position: [casingX, 1.55, 0],
        size: [0.62, 0.9, 0.62],
        axis: "y",
        tone: "guard",
      },
      {
        id: "compressor.bearing.de",
        label: "Compressor DE Housing",
        shape: "cylinder",
        position: [compDeX, AXIS_Y, 0],
        size: [0.5, 0.6, 0.5],
        tone: "casing",
      },
      {
        id: "compressor.bearing.nde",
        label: "Compressor NDE Housing",
        shape: "cylinder",
        position: [compNdeX, AXIS_Y, 0],
        size: [0.5, 0.6, 0.5],
        tone: "casing",
      },
      {
        id: "compressor.discharge",
        label: "Discharge Line",
        shape: "cylinder",
        position: [casingX + 1.7, 0.6, 0],
        size: [0.3, 0.9, 0.3],
        tone: "guard",
      },
      {
        id: "compressor.feet",
        label: "Compressor Frame",
        shape: "box",
        position: [casingX, BASE_TOP + 0.28, 0],
        size: [2.8, 0.55, 2.1],
        tone: "base",
      },
    ],
    bearingAnchors: [
      ...motor.bearingAnchors,
      { id: "compressor.de", label: "Compressor DE", position: [compDeX, AXIS_Y, 0], radius: 0.48 },
      { id: "compressor.nde", label: "Compressor NDE", position: [compNdeX, AXIS_Y, 0], radius: 0.48 },
    ],
    sensorAnchors: [
      ...motor.sensorAnchors,
      {
        id: "compressor.de",
        label: "Compressor DE",
        axisPoint: [compDeX, AXIS_Y, 0],
        radius: 0.5,
        axialFace: compDeX - 0.3,
        axialSign: -1,
      },
      {
        id: "compressor.nde",
        label: "Compressor NDE",
        axisPoint: [compNdeX, AXIS_Y, 0],
        radius: 0.5,
        axialFace: compNdeX + 0.3,
        axialSign: 1,
      },
      {
        id: "compressor.casing",
        label: "Compressor Housing",
        axisPoint: [casingX, 0.1, 0],
        radius: 1.05,
        axialFace: casingX + 1.3,
        axialSign: 1,
      },
      foundationAnchor(-1.4, 3.4),
    ],
    deBearingAnchorId: "compressor.de",
    ndeBearingAnchorId: "compressor.nde",
    mountingLocationMap: {
      "Motor DE": "motor.de",
      "Motor NDE": "motor.nde",
      "Bearing Housing DE": "compressor.de",
      "Bearing Housing NDE": "compressor.nde",
      "Compressor Housing": "compressor.casing",
      Foundation: "foundation",
    },
    fallbackAnchorId: "foundation",
  };
})();

/** Motor → gearbox, with the input and output shafts on different centres. */
const GEARBOX_MODEL: MachineModelSpec = (() => {
  const motor = drivingMotor(-2.6, 2.6, 0.9);
  const inputX = -1.25;
  const outputX = 1.55;
  const outputY = -0.55;

  return {
    id: "gearbox",
    label: "Gearbox",
    matches: ["Gearbox"],
    components: [
      basePlate(-1.5, 9.4, 3.0),
      ...motor.components,
      ...coupling(-1.95, 0.36),
      {
        id: "gearbox.housing",
        label: "Gearbox Housing",
        shape: "box",
        position: [0.2, -0.15, 0],
        size: [2.5, 2.5, 2.0],
        tone: "casing",
      },
      {
        id: "gearbox.input.shaft",
        label: "Input Shaft",
        shape: "cylinder",
        position: [-1.5, AXIS_Y, 0],
        size: [0.17, 1.4, 0.17],
        tone: "shaft",
      },
      {
        id: "gearbox.input.housing",
        label: "Input Bearing Housing",
        shape: "cylinder",
        position: [inputX, AXIS_Y, 0],
        size: [0.44, 0.5, 0.44],
        tone: "casing",
      },
      {
        id: "gearbox.output.shaft",
        label: "Output Shaft",
        shape: "cylinder",
        position: [2.05, outputY, 0],
        size: [0.26, 1.6, 0.26],
        tone: "shaft",
      },
      {
        id: "gearbox.output.housing",
        label: "Output Bearing Housing",
        shape: "cylinder",
        position: [outputX, outputY, 0],
        size: [0.52, 0.5, 0.52],
        tone: "casing",
      },
      {
        id: "gearbox.breather",
        label: "Breather / Fill",
        shape: "cylinder",
        position: [0.2, 1.35, 0],
        size: [0.18, 0.5, 0.18],
        axis: "y",
        tone: "guard",
      },
      {
        id: "gearbox.feet",
        label: "Gearbox Feet",
        shape: "box",
        position: [0.2, BASE_TOP + 0.25, 0],
        size: [2.7, 0.5, 2.2],
        tone: "base",
      },
    ],
    bearingAnchors: [
      ...motor.bearingAnchors,
      { id: "gearbox.input", label: "Gearbox Input", position: [inputX, AXIS_Y, 0], radius: 0.42 },
      { id: "gearbox.output", label: "Gearbox Output", position: [outputX, outputY, 0], radius: 0.5 },
    ],
    sensorAnchors: [
      ...motor.sensorAnchors,
      {
        id: "gearbox.input",
        label: "Gearbox Input",
        axisPoint: [inputX, AXIS_Y, 0],
        radius: 0.44,
        axialFace: inputX - 0.28,
        axialSign: -1,
      },
      {
        id: "gearbox.output",
        label: "Gearbox Output",
        axisPoint: [outputX, outputY, 0],
        radius: 0.52,
        axialFace: outputX + 0.28,
        axialSign: 1,
      },
      foundationAnchor(-1.5, 3.4),
    ],
    // A gearbox has no single "drive end" by name. The input (high-speed)
    // shaft carries the DE bearing number and the output the NDE, which is how
    // the two Step 3 fields line up with the two shafts on the box.
    deBearingAnchorId: "gearbox.input",
    ndeBearingAnchorId: "gearbox.output",
    mountingLocationMap: {
      "Motor DE": "motor.de",
      "Motor NDE": "motor.nde",
      "Gearbox Input": "gearbox.input",
      "Gearbox Output": "gearbox.output",
      "Bearing Housing DE": "gearbox.input",
      "Bearing Housing NDE": "gearbox.output",
      Foundation: "foundation",
    },
    fallbackAnchorId: "foundation",
  };
})();

/**
 * Stand-in for machine types without a dedicated model.
 *
 * Every rotating asset has the same three things a sensor gets mounted on — a
 * body, a shaft and two bearing housings — so a generic representation is
 * still useful. It is flagged `schematic` so the UI can say it is a generic
 * shape rather than a model of this particular machine.
 */
const GENERIC_MODEL: MachineModelSpec = (() => {
  const deX = 1.6;
  const ndeX = -1.6;

  return {
    id: "generic",
    label: "Generic Rotating Machine",
    matches: [],
    components: [
      basePlate(0, 6.0),
      {
        id: "generic.body",
        label: "Machine Body",
        shape: "box",
        position: [0, AXIS_Y, 0],
        size: [2.6, 1.9, 1.9],
        tone: "body",
      },
      {
        id: "generic.housing.de",
        label: "DE Bearing Housing",
        shape: "cylinder",
        position: [deX, AXIS_Y, 0],
        size: [0.5, 0.6, 0.5],
        tone: "casing",
      },
      {
        id: "generic.housing.nde",
        label: "NDE Bearing Housing",
        shape: "cylinder",
        position: [ndeX, AXIS_Y, 0],
        size: [0.5, 0.6, 0.5],
        tone: "casing",
      },
      {
        id: "generic.shaft",
        label: "Shaft",
        shape: "cylinder",
        position: [0, AXIS_Y, 0],
        size: [0.2, 5.0, 0.2],
        tone: "shaft",
      },
      {
        id: "generic.feet",
        label: "Feet",
        shape: "box",
        position: [0, BASE_TOP + 0.25, 0],
        size: [3.0, 0.5, 2.1],
        tone: "base",
      },
    ],
    bearingAnchors: [
      { id: "generic.de", label: "Drive End", position: [deX, AXIS_Y, 0], radius: 0.48 },
      { id: "generic.nde", label: "Non-Drive End", position: [ndeX, AXIS_Y, 0], radius: 0.48 },
    ],
    sensorAnchors: [
      {
        id: "generic.de",
        label: "Drive End",
        axisPoint: [deX, AXIS_Y, 0],
        radius: 0.5,
        axialFace: deX + 0.3,
        axialSign: 1,
      },
      {
        id: "generic.nde",
        label: "Non-Drive End",
        axisPoint: [ndeX, AXIS_Y, 0],
        radius: 0.5,
        axialFace: ndeX - 0.3,
        axialSign: -1,
      },
      foundationAnchor(0, 3.0),
    ],
    deBearingAnchorId: "generic.de",
    ndeBearingAnchorId: "generic.nde",
    mountingLocationMap: {
      "Bearing Housing DE": "generic.de",
      "Bearing Housing NDE": "generic.nde",
      "Motor DE": "generic.de",
      "Motor NDE": "generic.nde",
      Foundation: "foundation",
    },
    fallbackAnchorId: "foundation",
    schematic: true,
  };
})();

export const MACHINE_MODELS: MachineModelSpec[] = [
  MOTOR_MODEL,
  PUMP_MODEL,
  // The detailed motor-driven overhung fan, ported from the 3D reference.
  // Lives in its own module so it can be deleted when `fan.glb` lands.
  DETAILED_FAN_MODEL,
  COMPRESSOR_MODEL,
  GEARBOX_MODEL,
];

export const GENERIC_MACHINE_MODEL = GENERIC_MODEL;

/**
 * The model for a `machine_type`, falling back to the generic shape.
 *
 * A machine type with no dedicated model still gets a usable twin rather than
 * an empty panel — the Equipment Master must stay usable whatever is selected.
 */
export function resolveMachineModel(machineType: string | null | undefined): MachineModelSpec {
  const type = (machineType ?? "").trim().toLowerCase();
  if (!type) return GENERIC_MODEL;
  const match = MACHINE_MODELS.find((model) =>
    model.matches.some((candidate) => candidate.toLowerCase() === type)
  );
  return match ?? GENERIC_MODEL;
}

/** Axis-aligned bounds of a model, and the sphere that encloses it. */
export interface ModelBounds {
  centre: Vec3;
  size: Vec3;
  /** Radius of the bounding sphere — what the camera has to fit. */
  radius: number;
}

/** Half-size of one component along each axis, after its axis rotation. */
function halfExtents(spec: MachineComponentSpec): Vec3 {
  const [a, b, c] = spec.size;

  // A rotated part sweeps a larger box than its own dimensions. Rather than
  // compose the rotation properly, take the longest half-dimension on every
  // axis: framing may end up a shade generous, never too tight.
  if (spec.rotation) {
    const reach = Math.max(a, b, c) / 2;
    return [reach, reach, reach];
  }

  if (spec.shape === "box") return [a / 2, b / 2, c / 2];

  const radius = Math.max(a, c);
  const axis = spec.axis ?? "x";
  if (axis === "x") return [b / 2, radius, radius];
  if (axis === "y") return [radius, b / 2, radius];
  return [radius, radius, b / 2];
}

const boundsCache = new WeakMap<MachineModelSpec, ModelBounds>();

/**
 * What the camera has to frame.
 *
 * Derived from the component specs rather than hand-tuned per model, so a
 * model added to the registry frames itself correctly with nothing else to
 * set — and a model whose layout is not centred on the origin (the pump and
 * fan sets run well off to -X) is still centred in the view.
 */
export function modelBounds(model: MachineModelSpec): ModelBounds {
  const cached = boundsCache.get(model);
  if (cached) return cached;

  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];

  model.components.forEach((spec) => {
    const half = halfExtents(spec);
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], spec.position[axis] - half[axis]);
      max[axis] = Math.max(max[axis], spec.position[axis] + half[axis]);
    }
  });

  const centre: Vec3 = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ];
  const size: Vec3 = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  const radius = Math.hypot(size[0], size[1], size[2]) / 2;

  const bounds: ModelBounds = { centre, size, radius };
  boundsCache.set(model, bounds);
  return bounds;
}

export function findBearingAnchor(
  model: MachineModelSpec,
  anchorId: string
): BearingAnchorSpec | null {
  return model.bearingAnchors.find((anchor) => anchor.id === anchorId) ?? null;
}

export function findSensorAnchor(
  model: MachineModelSpec,
  anchorId: string
): SensorAnchorSpec | null {
  return model.sensorAnchors.find((anchor) => anchor.id === anchorId) ?? null;
}

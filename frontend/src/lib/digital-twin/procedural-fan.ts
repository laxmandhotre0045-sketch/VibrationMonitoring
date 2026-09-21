/**
 * Digital Twin — the detailed motor-driven overhung fan.
 *
 * This is the reference machine from `digital-twin-3d.html`, rebuilt as a
 * registry spec: finned motor, coupling under a guard, two bearing pedestals
 * on plinths, and an impeller overhung beyond them inside a scroll housing.
 *
 * Kept in its own module on purpose. Once `public/models/fan.glb` exists this
 * file and its one reference from `machine-registry.ts` are the whole deletion
 * — nothing else imports it.
 *
 * Layout along +X (the shaft axis), left to right:
 *
 *   motor NDE ── motor body ── motor DE ── coupling ── fan DE ── fan NDE ── impeller
 *
 * "Overhung" is the point: both fan bearings sit between the coupling and the
 * impeller, so the impeller hangs outboard of the bearing span. That is what
 * makes the axial sensor on the fan NDE the interesting one, and it is why the
 * pedestals are where the six standard mounting rows land.
 */

import type { MachineComponentSpec, MachineModelSpec, Vec3 } from "./types";

const AXIS_Y = 0;
const BASE_TOP = -1.45;

// Stations along the shaft.
const MOTOR_NDE_X = -5.35;
const MOTOR_DE_X = -3.05;
const COUPLING_X = -2.15;
const FAN_DE_X = -1.05;
const FAN_NDE_X = 0.35;
const HOUSING_X = 2.15;

const MOTOR_RADIUS = 1.0;
const PEDESTAL_RADIUS = 0.44;
const HOUSING_RADIUS = 1.9;

function plinth(id: string, centreX: number, length: number, depth: number): MachineComponentSpec {
  return {
    id,
    label: "Plinth",
    shape: "box",
    position: [centreX, BASE_TOP - 0.28, 0],
    size: [length, 0.56, depth],
    tone: "base",
    xray: false,
  };
}

/** Longitudinal cooling fins around the motor body. */
function coolingFins(centreX: number, length: number, count = 18): MachineComponentSpec[] {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2;
    return {
      id: `motor.fin.${i}`,
      label: "Cooling Fin",
      shape: "box" as const,
      position: [
        centreX,
        AXIS_Y + Math.cos(angle) * (MOTOR_RADIUS + 0.07),
        Math.sin(angle) * (MOTOR_RADIUS + 0.07),
      ] as Vec3,
      size: [length, 0.16, 0.05] as Vec3,
      rotation: [-angle, 0, 0] as Vec3,
      tone: "casing" as const,
    };
  });
}

/** A bearing pedestal: pillow block on a column down to its plinth. */
function pedestal(id: string, centreX: number, label: string): MachineComponentSpec[] {
  return [
    {
      id: `${id}.block`,
      label,
      shape: "cylinder",
      position: [centreX, AXIS_Y, 0],
      size: [PEDESTAL_RADIUS, 0.5, PEDESTAL_RADIUS],
      tone: "casing",
    },
    {
      id: `${id}.cap`,
      label: `${label} Cap`,
      shape: "box",
      position: [centreX, AXIS_Y + 0.3, 0],
      size: [0.52, 0.28, 0.72],
      tone: "casing",
    },
    {
      id: `${id}.column`,
      label: `${label} Pedestal`,
      shape: "box",
      position: [centreX, (BASE_TOP - PEDESTAL_RADIUS) / 2, 0],
      size: [0.6, -BASE_TOP - PEDESTAL_RADIUS, 0.8],
      tone: "base",
      xray: false,
    },
  ];
}

/** Backward-curved impeller blades on a hub — the part that spins. */
function impeller(centreX: number, count = 11): MachineComponentSpec[] {
  const blades = Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2;
    return {
      id: `fan.blade.${i}`,
      label: "Impeller Blade",
      shape: "box" as const,
      position: [
        centreX,
        AXIS_Y + Math.cos(angle) * 1.02,
        Math.sin(angle) * 1.02,
      ] as Vec3,
      size: [0.62, 0.95, 0.08] as Vec3,
      // Tilted off pure radial so the blades read as backward-curved rather
      // than as a flat paddle wheel.
      rotation: [-angle + 0.42, 0, 0] as Vec3,
      tone: "shaft" as const,
      spin: true,
      xray: false,
    };
  });

  return [
    {
      id: "fan.hub",
      label: "Impeller Hub",
      shape: "cylinder",
      position: [centreX, AXIS_Y, 0],
      size: [0.34, 0.6, 0.34],
      tone: "shaft",
      spin: true,
      xray: false,
    },
    {
      id: "fan.backplate",
      label: "Impeller Back Plate",
      shape: "cylinder",
      position: [centreX - 0.34, AXIS_Y, 0],
      size: [1.42, 0.07, 1.42],
      tone: "shaft",
      spin: true,
      xray: false,
    },
    ...blades,
  ];
}

export const DETAILED_FAN_MODEL: MachineModelSpec = {
  id: "fan",
  label: "Motor-Driven Overhung Fan",
  matches: ["Fan", "Blower"],

  components: [
    plinth("base.motor", -4.2, 3.3, 2.4),
    plinth("base.pedestals", -0.35, 2.6, 1.5),
    plinth("base.housing", HOUSING_X, 2.6, 3.0),

    // --- Motor -----------------------------------------------------------
    {
      id: "motor.casing",
      label: "Motor Body",
      shape: "cylinder",
      position: [-4.2, AXIS_Y, 0],
      size: [MOTOR_RADIUS, 2.3, MOTOR_RADIUS],
      tone: "body",
    },
    ...coolingFins(-4.2, 2.1),
    {
      id: "motor.bell.nde",
      label: "Motor NDE End Bell",
      shape: "cylinder",
      position: [MOTOR_NDE_X + 0.13, AXIS_Y, 0],
      size: [0.88, 0.28, 0.88],
      tone: "casing",
    },
    {
      id: "motor.bell.de",
      label: "Motor DE End Bell",
      shape: "cylinder",
      position: [MOTOR_DE_X - 0.13, AXIS_Y, 0],
      size: [0.88, 0.28, 0.88],
      tone: "casing",
    },
    {
      id: "motor.cowl",
      label: "Cooling Fan Cowl",
      shape: "cylinder",
      position: [MOTOR_NDE_X - 0.25, AXIS_Y, 0],
      size: [0.78, 0.5, 0.78],
      tone: "guard",
    },
    {
      id: "motor.terminal.housing",
      label: "Terminal Box",
      shape: "box",
      position: [-4.2, MOTOR_RADIUS + 0.4, 0],
      size: [1.1, 0.5, 0.86],
      tone: "casing",
    },
    {
      id: "motor.feet",
      label: "Motor Feet",
      shape: "box",
      position: [-4.2, (BASE_TOP - MOTOR_RADIUS) / 2, 0],
      size: [2.1, -BASE_TOP - MOTOR_RADIUS, 2.15],
      tone: "base",
      xray: false,
    },
    {
      id: "motor.rotor.core",
      label: "Rotor Core",
      shape: "cylinder",
      position: [-4.2, AXIS_Y, 0],
      size: [0.62, 2.0, 0.62],
      tone: "shaft",
      spin: true,
      xray: false,
    },

    // --- Shaft line ------------------------------------------------------
    {
      id: "shaft.motor",
      label: "Motor Shaft",
      shape: "cylinder",
      position: [-2.6, AXIS_Y, 0],
      size: [0.15, 5.6, 0.15],
      tone: "shaft",
      spin: true,
      xray: false,
    },
    {
      id: "shaft.fan",
      label: "Fan Shaft",
      shape: "cylinder",
      position: [0.4, AXIS_Y, 0],
      size: [0.17, 4.2, 0.17],
      tone: "shaft",
      spin: true,
      xray: false,
    },
    {
      id: "coupling",
      label: "Coupling",
      shape: "cylinder",
      position: [COUPLING_X, AXIS_Y, 0],
      size: [0.4, 0.62, 0.4],
      tone: "shaft",
      spin: true,
      xray: false,
    },
    {
      id: "coupling.guard",
      label: "Coupling Guard",
      shape: "cylinder",
      position: [COUPLING_X, AXIS_Y, 0],
      size: [0.62, 0.95, 0.62],
      tone: "guard",
    },

    // --- Fan bearings ----------------------------------------------------
    ...pedestal("fan.de", FAN_DE_X, "Fan DE Pillow Block"),
    ...pedestal("fan.nde", FAN_NDE_X, "Fan NDE Pillow Block"),

    // --- Scroll housing and impeller -------------------------------------
    {
      id: "fan.housing",
      label: "Fan Housing (Scroll)",
      shape: "cylinder",
      position: [HOUSING_X, AXIS_Y, 0],
      size: [HOUSING_RADIUS, 1.35, HOUSING_RADIUS],
      tone: "casing",
    },
    {
      id: "fan.housing.inlet.cover",
      label: "Inlet Cone",
      shape: "cone",
      position: [HOUSING_X + 0.95, AXIS_Y, 0],
      size: [0.78, 0.6, 1.25],
      tone: "guard",
    },
    {
      id: "fan.outlet.casing",
      label: "Outlet Duct",
      shape: "box",
      position: [HOUSING_X, HOUSING_RADIUS + 0.55, 0],
      size: [1.35, 1.1, 1.5],
      tone: "casing",
    },
    ...impeller(HOUSING_X),
  ],

  bearingAnchors: [
    { id: "motor.nde", label: "Motor NDE", position: [MOTOR_NDE_X, AXIS_Y, 0], radius: 0.46 },
    { id: "motor.de", label: "Motor DE", position: [MOTOR_DE_X, AXIS_Y, 0], radius: 0.46 },
    { id: "fan.de", label: "Fan DE", position: [FAN_DE_X, AXIS_Y, 0], radius: PEDESTAL_RADIUS },
    { id: "fan.nde", label: "Fan NDE", position: [FAN_NDE_X, AXIS_Y, 0], radius: PEDESTAL_RADIUS },
  ],

  sensorAnchors: [
    {
      id: "motor.de",
      label: "Motor DE",
      axisPoint: [MOTOR_DE_X - 0.13, AXIS_Y, 0],
      radius: 0.88,
      axialFace: MOTOR_DE_X,
      axialSign: 1,
    },
    {
      id: "motor.nde",
      label: "Motor NDE",
      axisPoint: [MOTOR_NDE_X + 0.13, AXIS_Y, 0],
      radius: 0.88,
      axialFace: MOTOR_NDE_X,
      axialSign: -1,
    },
    {
      id: "fan.de",
      label: "Fan DE housing",
      axisPoint: [FAN_DE_X, AXIS_Y, 0],
      radius: PEDESTAL_RADIUS,
      axialFace: FAN_DE_X - 0.27,
      axialSign: -1,
    },
    {
      id: "fan.nde",
      label: "Fan NDE housing",
      axisPoint: [FAN_NDE_X, AXIS_Y, 0],
      radius: PEDESTAL_RADIUS,
      axialFace: FAN_NDE_X + 0.27,
      axialSign: 1,
    },
    {
      id: "fan.housing",
      label: "Fan Housing",
      axisPoint: [HOUSING_X, AXIS_Y, 0],
      radius: HOUSING_RADIUS,
      axialFace: HOUSING_X + 0.68,
      axialSign: 1,
    },
    {
      id: "foundation",
      label: "Foundation",
      axisPoint: [-1.2, BASE_TOP, 0],
      radius: 0.35,
      axialFace: 3.4,
      axialSign: 1,
      static: true,
    },
  ],

  // The six standard mounting rows land on the two fan pedestals, which is
  // where an analyst actually mounts on an overhung fan.
  deBearingAnchorId: "fan.de",
  ndeBearingAnchorId: "fan.nde",
  mountingLocationMap: {
    "Bearing Housing DE": "fan.de",
    "Bearing Housing NDE": "fan.nde",
    "Motor DE": "motor.de",
    "Motor NDE": "motor.nde",
    "Fan Housing": "fan.housing",
    Foundation: "foundation",
  },
  fallbackAnchorId: "foundation",
};

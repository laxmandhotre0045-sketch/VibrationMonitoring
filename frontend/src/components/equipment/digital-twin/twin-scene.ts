/**
 * Digital Twin — three.js object construction and teardown.
 *
 * Everything that touches three lives here or in `DigitalTwinViewer`. The
 * builders take the resolved configuration from `lib/digital-twin` and return
 * a `THREE.Group`; `disposeObject` gives every one of them back.
 *
 * Disposal matters more than usual here: the twin is rebuilt on every form
 * keystroke that changes the configuration, so a geometry or texture left
 * undisposed would leak once per keystroke for as long as the form is open.
 */

import * as THREE from "three";
import { modelBounds } from "@/lib/digital-twin/machine-registry";
import type {
  BearingAnchorSpec,
  ComponentTone,
  MachineComponentSpec,
  MachineModelSpec,
  ResolvedTwin,
  Vec3,
} from "@/lib/digital-twin/types";

/** SensoVibe palette, carried into the 3D scene. */
const COLORS = {
  body: 0x3f5f92,
  casing: 0x6b86b5,
  shaft: 0x9aa7bc,
  base: 0x8a97a8,
  guard: 0xc3cee0,
  edge: 0x15366d,
  bearing: 0xf5a623,
  bearingGhost: 0xbcc7d6,
  sensor: 0xff6b00,
  sensorUnmapped: 0x94a3b8,
  ground: 0xe8edf5,
} as const;

const TONE_COLOR: Record<ComponentTone, number> = {
  body: COLORS.body,
  casing: COLORS.casing,
  shaft: COLORS.shaft,
  base: COLORS.base,
  guard: COLORS.guard,
};

export const BACKGROUND_COLOR = 0xfffdf8;

/** Vertical field of view. Shared with the framing maths below. */
export const CAMERA_FOV = 42;

/** Named camera directions. Distance is computed from the model's bounds. */
export const CAMERA_VIEWS = {
  iso: [1.05, 0.5, 1.4],
  front: [0, 0.12, 2.1],
  side: [2.1, 0.12, 0.02],
  top: [0.02, 2.2, 0.02],
} as const;

export type CameraViewId = keyof typeof CAMERA_VIEWS;

function vec(v: Vec3): THREE.Vector3 {
  return new THREE.Vector3(v[0], v[1], v[2]);
}

// ---------------------------------------------------------------------------
// Disposal
// ---------------------------------------------------------------------------

function disposeMaterial(material: THREE.Material) {
  // Sprite and mesh materials can both own a texture; a CanvasTexture left
  // behind holds its backing bitmap alive.
  const withMap = material as THREE.Material & { map?: THREE.Texture | null };
  if (withMap.map) withMap.map.dispose();
  material.dispose();
}

/**
 * Release every GPU resource under `root`, then detach it from its parent.
 *
 * Safe to call on an object that was never added to a scene.
 */
export function disposeObject(root: THREE.Object3D | null | undefined) {
  if (!root) return;

  root.traverse((child) => {
    const withGeometry = child as THREE.Object3D & { geometry?: THREE.BufferGeometry };
    if (withGeometry.geometry) withGeometry.geometry.dispose();

    const withMaterial = child as THREE.Object3D & {
      material?: THREE.Material | THREE.Material[];
    };
    const material = withMaterial.material;
    if (Array.isArray(material)) material.forEach(disposeMaterial);
    else if (material) disposeMaterial(material);
  });

  root.removeFromParent();
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

type LabelVariant = "channel" | "bearing" | "muted";

const LABEL_STYLE: Record<LabelVariant, { fill: string; text: string; border: string }> = {
  channel: { fill: "#FF6B00", text: "#FFFFFF", border: "#E55F00" },
  bearing: { fill: "#F5A623", text: "#2B1A00", border: "#D98C00" },
  muted: { fill: "#FFFFFF", text: "#5A6779", border: "#C9D2E0" },
};

const LABEL_FONT_PX = 46;
const LABEL_PAD_PX = 22;
const LABEL_WORLD_HEIGHT = 0.3;

/**
 * A camera-facing text chip.
 *
 * Canvas-backed rather than an HTML overlay so the label is occluded and
 * scaled by the scene like everything else. The texture is owned by the
 * sprite's material and released by `disposeObject`.
 */
export function createLabelSprite(text: string, variant: LabelVariant): THREE.Sprite {
  const style = LABEL_STYLE[variant];
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");

  const measureFont = `600 ${LABEL_FONT_PX}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  let textWidth = text.length * LABEL_FONT_PX * 0.56;
  if (context) {
    context.font = measureFont;
    textWidth = context.measureText(text).width;
  }

  const width = Math.ceil(textWidth + LABEL_PAD_PX * 2);
  const height = Math.ceil(LABEL_FONT_PX + LABEL_PAD_PX * 1.1);
  canvas.width = width;
  canvas.height = height;

  if (context) {
    const radius = height / 2;
    context.font = measureFont;
    context.textAlign = "center";
    context.textBaseline = "middle";

    context.beginPath();
    // roundRect is recent enough that a plain rect is worth keeping as a
    // fallback — a missing method here would take down the whole viewer.
    if (typeof context.roundRect === "function") {
      context.roundRect(2, 2, width - 4, height - 4, radius);
    } else {
      context.rect(2, 2, width - 4, height - 4);
    }
    context.fillStyle = style.fill;
    context.fill();
    context.lineWidth = 3;
    context.strokeStyle = style.border;
    context.stroke();

    context.fillStyle = style.text;
    context.fillText(text, width / 2, height / 2 + 1);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false })
  );
  sprite.scale.set((width / height) * LABEL_WORLD_HEIGHT, LABEL_WORLD_HEIGHT, 1);
  // Labels sit above the geometry they annotate rather than inside it.
  sprite.renderOrder = 10;
  return sprite;
}

// ---------------------------------------------------------------------------
// Machine
// ---------------------------------------------------------------------------

function componentGeometry(spec: MachineComponentSpec): THREE.BufferGeometry {
  const [a, b, c] = spec.size;

  if (spec.shape === "box") {
    return new THREE.BoxGeometry(a, b, c);
  }

  const geometry =
    spec.shape === "cone"
      ? new THREE.CylinderGeometry(a, c, b, 28, 1)
      : new THREE.CylinderGeometry(a, c, b, 32, 1);

  // Cylinders are built along Y; rotate to the axis the spec asks for.
  const axis = spec.axis ?? "x";
  if (axis === "x") geometry.rotateZ(Math.PI / 2);
  else if (axis === "z") geometry.rotateX(Math.PI / 2);

  return geometry;
}

/**
 * The machine itself: one mesh per component, each with a navy edge overlay
 * so the shape reads as an engineering drawing rather than a blob of colour.
 */
export function buildMachineGroup(model: MachineModelSpec): THREE.Group {
  const group = new THREE.Group();
  group.name = "machine";

  model.components.forEach((spec) => {
    const geometry = componentGeometry(spec);
    const material = new THREE.MeshLambertMaterial({
      color: TONE_COLOR[spec.tone ?? "body"],
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.copy(vec(spec.position));
    mesh.userData.componentId = spec.id;
    group.add(mesh);

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 32),
      new THREE.LineBasicMaterial({ color: COLORS.edge, transparent: true, opacity: 0.32 })
    );
    edges.position.copy(mesh.position);
    group.add(edges);
  });

  return group;
}

/** A soft ground plane, so the machine reads as standing on something. */
export function buildGroundGroup(model: MachineModelSpec): THREE.Group {
  const group = new THREE.Group();
  group.name = "ground";

  const bounds = modelBounds(model);
  const size = Math.max(bounds.size[0], bounds.size[2]) * 1.8;
  const grid = new THREE.GridHelper(size, Math.round(size / 0.8), COLORS.ground, COLORS.ground);
  grid.position.set(bounds.centre[0], -1.78, 0);
  const gridMaterial = grid.material as THREE.Material;
  gridMaterial.transparent = true;
  gridMaterial.opacity = 0.55;
  group.add(grid);

  return group;
}

// ---------------------------------------------------------------------------
// Bearings
// ---------------------------------------------------------------------------

function bearingRing(anchor: BearingAnchorSpec, configured: boolean): THREE.Mesh {
  const geometry = new THREE.TorusGeometry(anchor.radius, anchor.radius * 0.26, 12, 36);
  // The torus is built in the XY plane; stand it up around the shaft.
  geometry.rotateY(Math.PI / 2);

  const material = new THREE.MeshLambertMaterial({
    color: configured ? COLORS.bearing : COLORS.bearingGhost,
    transparent: !configured,
    opacity: configured ? 1 : 0.38,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(vec(anchor.position));
  return mesh;
}

/**
 * Configured bearings, plus a faint outline at any bearing position the form
 * has left blank.
 *
 * The outline is deliberately not a bearing: Step 3 is optional, and an empty
 * field must not read as a fitted part.
 */
export function buildBearingGroup(twin: ResolvedTwin): THREE.Group {
  const group = new THREE.Group();
  group.name = "bearings";

  twin.ghostBearingAnchors.forEach((anchor) => {
    const ring = bearingRing(anchor, false);
    ring.userData.pick = null;
    group.add(ring);
  });

  twin.bearings.forEach((bearing) => {
    const ring = bearingRing(bearing.anchor, true);
    ring.userData.pick = { kind: "bearing", key: bearing.key };
    group.add(ring);

    const label = createLabelSprite(
      bearing.bearingNumber
        ? `${bearing.position} · ${bearing.bearingNumber}`
        : `${bearing.position} bearing`,
      "bearing"
    );
    // Under the ring, and staggered along the shaft — DE back toward -X, NDE
    // forward toward +X. Two bearing chips on one machine would otherwise
    // overlap each other on a short set like a pump, where the two housings sit
    // barely a unit apart. Below the shaft is also the one direction no sensor
    // orientation points: Vertical goes up, Horizontal across, Axial along.
    label.position.set(
      bearing.anchor.position[0] + (bearing.position === "DE" ? -0.55 : 0.55),
      bearing.anchor.position[1] - bearing.anchor.radius - 0.52,
      bearing.anchor.position[2]
    );
    // The chip is the easiest thing to hit, so it picks the same bearing.
    label.userData.pick = { kind: "bearing", key: bearing.key };
    group.add(label);
  });

  return group;
}

// ---------------------------------------------------------------------------
// Sensors
// ---------------------------------------------------------------------------

/**
 * The orientation arrow.
 *
 * Built from the sensor's direction vector rather than drawn per orientation,
 * so Horizontal, Vertical, Axial, Radial and Tangential all come out of the
 * same code and a changed orientation just re-points the arrow.
 */
function orientationArrow(direction: Vec3, color: number): THREE.Group {
  const group = new THREE.Group();
  const length = 0.52;
  const headLength = 0.17;

  const shaftGeometry = new THREE.CylinderGeometry(0.028, 0.028, length - headLength, 10);
  shaftGeometry.translate(0, (length - headLength) / 2, 0);
  group.add(new THREE.Mesh(shaftGeometry, new THREE.MeshLambertMaterial({ color })));

  const headGeometry = new THREE.ConeGeometry(0.075, headLength, 14);
  headGeometry.translate(0, length - headLength / 2, 0);
  group.add(new THREE.Mesh(headGeometry, new THREE.MeshLambertMaterial({ color })));

  // The arrow is authored pointing +Y; aim it along the orientation.
  group.quaternion.setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    vec(direction).normalize()
  );
  return group;
}

/**
 * One marker per configured sensor: a puck on the machine surface, a channel
 * chip, and an arrow showing which way it measures.
 */
export function buildSensorGroup(twin: ResolvedTwin): THREE.Group {
  const group = new THREE.Group();
  group.name = "sensors";

  twin.sensors.forEach((sensor) => {
    const color = sensor.mapped ? COLORS.sensor : COLORS.sensorUnmapped;
    const origin = vec(sensor.markerPosition);

    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.15, 20, 14),
      new THREE.MeshLambertMaterial({ color })
    );
    marker.position.copy(origin);
    marker.userData.pick = { kind: "sensor", key: sensor.key };
    group.add(marker);

    // A wider, flatter halo so small markers stay easy to hit and to see
    // against the machine body.
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(0.26, 16, 12),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16 })
    );
    halo.position.copy(origin);
    halo.userData.pick = { kind: "sensor", key: sensor.key };
    group.add(halo);

    const arrow = orientationArrow(sensor.direction, color);
    arrow.position.copy(origin);
    group.add(arrow);

    const label = createLabelSprite(sensor.channel, sensor.mapped ? "channel" : "muted");
    label.position
      .copy(origin)
      .addScaledVector(vec(sensor.direction).normalize(), 0.92);
    label.userData.pick = { kind: "sensor", key: sensor.key };
    group.add(label);
  });

  return group;
}

// ---------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------

/** Headroom around the model, leaving space for the sensor labels. */
const FRAMING_MARGIN = 1.16;

export interface Framing {
  position: THREE.Vector3;
  target: THREE.Vector3;
  minDistance: number;
  maxDistance: number;
}

/**
 * Where to put the camera so the whole machine is in shot.
 *
 * Fits the model's eight bounding-box corners to *both* fields of view, rather
 * than fitting its bounding sphere. A pump set is roughly 9 units long and 3
 * tall, so its bounding sphere is nearly three times its height — fitting that
 * sphere vertically would push the camera far enough back to leave the machine
 * a smudge in the middle of a wide panel. Projecting the real corners frames
 * it tightly from any angle, at any aspect, with no per-model tuning.
 *
 * The target is the model's own centre, which matters because the pump, fan,
 * compressor and gearbox sets are laid out well off the origin.
 */
export function framingFor(
  view: CameraViewId,
  model: MachineModelSpec,
  aspect: number
): Framing {
  const { centre, size, radius } = modelBounds(model);

  const vFov = (CAMERA_FOV * Math.PI) / 180;
  const tanV = Math.tan(vFov / 2);
  const tanH = tanV * Math.max(aspect, 0.2);

  // Camera basis: `dir` runs from the target out toward the camera.
  const dir = new THREE.Vector3(...CAMERA_VIEWS[view]).normalize();
  const reference =
    Math.abs(dir.y) > 0.98 ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0);
  const right = new THREE.Vector3().crossVectors(reference, dir).normalize();
  const up = new THREE.Vector3().crossVectors(dir, right).normalize();

  const half = [size[0] / 2, size[1] / 2, size[2] / 2];
  const corner = new THREE.Vector3();
  let distance = 0;

  for (let i = 0; i < 8; i += 1) {
    corner.set(
      (i & 1 ? 1 : -1) * half[0],
      (i & 2 ? 1 : -1) * half[1],
      (i & 4 ? 1 : -1) * half[2]
    );
    // Depth toward the camera, plus how far out the corner sits on screen.
    const depth = corner.dot(dir);
    const across = Math.abs(corner.dot(right)) * FRAMING_MARGIN;
    const above = Math.abs(corner.dot(up)) * FRAMING_MARGIN;
    distance = Math.max(distance, depth + across / tanH, depth + above / tanV);
  }

  const target = new THREE.Vector3(centre[0], centre[1], centre[2]);
  const position = dir.clone().multiplyScalar(distance).add(target);

  return { position, target, minDistance: radius * 0.35, maxDistance: radius * 10 };
}

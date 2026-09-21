/**
 * Digital Twin — procedural model source.
 *
 * Builds a `TwinModelSource` from the registry specs, so a machine type with
 * no GLB yet still gets a real, lit, interactive model rather than a "not
 * available" panel.
 *
 * The important part is that it produces **exactly the same shape** the GLB
 * loader does: named `CH_*` and `BRG_*` empties, an x-ray mesh list and a
 * ROTOR group. Downstream — markers, labels, x-ray, occlusion — nothing knows
 * or cares which source it got.
 *
 * Anchor placement reuses `orientationDirection` and `markerPosition` from
 * `twin-config`, so the geometry here and the v1 viewer agree on where a
 * horizontal sensor on the motor DE actually sits.
 */

import * as THREE from "three";
import {
  MACHINE_MODELS,
  GENERIC_MACHINE_MODEL,
  modelBounds,
} from "@/lib/digital-twin/machine-registry";
import { markerPosition, orientationDirection } from "@/lib/digital-twin/twin-config";
import { bearingNodeName, sensorNodeName } from "@/lib/digital-twin/machine-type-map";
import type {
  ComponentTone,
  MachineComponentSpec,
  MachineModelSpec,
  SensorOrientation,
  TwinModelSource,
} from "@/lib/digital-twin/types";

const ORIENTATIONS: SensorOrientation[] = [
  "Horizontal",
  "Vertical",
  "Axial",
  "Radial",
  "Tangential",
];

interface ToneMaterial {
  color: number;
  roughness: number;
  metalness: number;
}

const TONE: Record<ComponentTone, ToneMaterial> = {
  body: { color: 0x3f5f92, roughness: 0.55, metalness: 0.35 },
  casing: { color: 0x6b86b5, roughness: 0.45, metalness: 0.5 },
  shaft: { color: 0xb9c2d0, roughness: 0.22, metalness: 0.95 },
  base: { color: 0x8a97a8, roughness: 0.8, metalness: 0.15 },
  guard: { color: 0xc3cee0, roughness: 0.5, metalness: 0.3 },
};

/**
 * Which tones form the x-ray layer.
 *
 * On these schematic models the outer *body* is the casing — fading only the
 * parts literally named "casing" would leave a motor's shell opaque and make
 * x-ray do nothing. Shaft and base stay solid so the machine keeps its shape
 * when the shells go.
 */
const XRAY_TONES: ReadonlySet<ComponentTone> = new Set<ComponentTone>([
  "body",
  "casing",
  "guard",
]);

function componentGeometry(spec: MachineComponentSpec): THREE.BufferGeometry {
  const [a, b, c] = spec.size;
  if (spec.shape === "box") return new THREE.BoxGeometry(a, b, c);

  const geometry =
    spec.shape === "cone"
      ? new THREE.CylinderGeometry(a, c, b, 32, 1)
      : new THREE.CylinderGeometry(a, c, b, 40, 1);

  const axis = spec.axis ?? "x";
  if (axis === "x") geometry.rotateZ(Math.PI / 2);
  else if (axis === "z") geometry.rotateX(Math.PI / 2);
  return geometry;
}

/** An empty whose local +Y points along `direction`, per the anchor contract. */
function createAnchor(
  name: string,
  position: THREE.Vector3Like,
  direction?: THREE.Vector3
): THREE.Object3D {
  const anchor = new THREE.Object3D();
  anchor.name = name;
  anchor.position.set(position.x, position.y, position.z);
  if (direction) {
    anchor.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      direction.clone().normalize()
    );
  }
  return anchor;
}

export function findProceduralModel(modelId: string): MachineModelSpec {
  return (
    MACHINE_MODELS.find((model) => model.id === modelId) ?? GENERIC_MACHINE_MODEL
  );
}

export function buildProceduralSource(modelId: string): TwinModelSource {
  const model = findProceduralModel(modelId);

  const root = new THREE.Group();
  root.name = `procedural:${model.id}`;

  const xrayMeshes: THREE.Mesh[] = [];
  const rotor = new THREE.Group();
  rotor.name = "ROTOR";
  root.add(rotor);

  model.components.forEach((spec) => {
    const tone = spec.tone ?? "body";
    const settings = TONE[tone];
    const mesh = new THREE.Mesh(
      componentGeometry(spec),
      new THREE.MeshStandardMaterial({
        color: settings.color,
        roughness: settings.roughness,
        metalness: settings.metalness,
      })
    );
    mesh.name = spec.id;
    mesh.position.set(spec.position[0], spec.position[1], spec.position[2]);
    if (spec.rotation) {
      mesh.rotation.set(spec.rotation[0], spec.rotation[1], spec.rotation[2]);
    }
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    // An explicit `xray` flag wins over the tone default: an impeller inside a
    // scroll housing is "shaft"-toned but must stay solid, and a plinth must
    // never fade out from under the machine.
    const inXrayLayer = spec.xray ?? XRAY_TONES.has(tone);
    if (inXrayLayer) {
      // Read by the x-ray controller, exactly as a GLB mesh named "…casing…"
      // would be. One flag, one code path for both sources.
      mesh.userData.xray = true;
      xrayMeshes.push(mesh);
    }

    // `spin` is the explicit answer. Without it, fall back to inferring from
    // the tone: only shafts that actually run down the model's centre line
    // join ROTOR, because a gearbox output shaft on its own centre would orbit
    // rather than spin when rotated about the group's origin. Impeller blades
    // sit off-centre by design and are marked `spin` instead.
    const spins =
      spec.spin ??
      (tone === "shaft" &&
        Math.abs(spec.position[1]) < 0.05 &&
        Math.abs(spec.position[2]) < 0.05);
    if (spins) rotor.add(mesh);
    else root.add(mesh);
  });

  const bearingAnchors = new Map<string, THREE.Object3D>();
  model.bearingAnchors.forEach((anchor) => {
    const name = bearingNodeName(anchor.id);
    const node = createAnchor(name, {
      x: anchor.position[0],
      y: anchor.position[1],
      z: anchor.position[2],
    });
    node.userData.radius = anchor.radius;
    node.userData.label = anchor.label;
    root.add(node);
    bearingAnchors.set(name, node);
  });

  // One empty per mounting point per axis. They are empties, so the full cross
  // product costs nothing and guarantees the adapter's node name always
  // resolves — no "anchor missing" path on the procedural side.
  const sensorAnchors = new Map<string, THREE.Object3D>();
  model.sensorAnchors.forEach((anchor) => {
    ORIENTATIONS.forEach((orientation) => {
      const direction = orientationDirection(orientation, anchor);
      const position = markerPosition(anchor, orientation, direction, 0);
      const name = sensorNodeName(anchor.id, orientation);
      const node = createAnchor(
        name,
        { x: position[0], y: position[1], z: position[2] },
        new THREE.Vector3(direction[0], direction[1], direction[2])
      );
      node.userData.label = anchor.label;
      root.add(node);
      sensorAnchors.set(name, node);
    });
  });

  // Drop the model onto y = 0 so the shadow floor and the GLB path agree on
  // where "the ground" is.
  const bounds = modelBounds(model);
  root.position.y = -(bounds.centre[1] - bounds.size[1] / 2);

  return {
    root,
    sensorAnchors,
    bearingAnchors,
    xrayMeshes,
    rotor: rotor.children.length > 0 ? rotor : null,
    kind: "procedural",
    schematic: model.schematic === true,
  };
}

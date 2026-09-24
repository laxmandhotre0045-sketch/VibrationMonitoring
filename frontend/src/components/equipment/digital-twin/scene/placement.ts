/**
 * Digital Twin — free sensor placement.
 *
 * A sensor normally sits on a named anchor: the model says where "Motor DE"
 * is, and the orientation pushes the instrument out to the surface. That covers
 * the standard mounting points, and it is what keeps a saved twin meaningful
 * when the model is later revised.
 *
 * Real machines do not always cooperate. An accelerometer goes where there is a
 * flat, where the casing is thick enough for a stud, or where a cable can
 * actually be run — and that is often somewhere the model has no anchor for.
 * This module is the escape hatch: it turns a ray hit on the machine's surface
 * into a placement, and a placement back into a transform.
 *
 * Two decisions worth knowing about.
 *
 * **Placements are stored in the model root's local space**, not in world
 * space. The root gets recentred and framed when a model loads, so a world
 * position would drift the first time the same machine was opened at a
 * different size.
 *
 * **The surface normal travels with the point.** Without it a dragged sensor
 * would stand upright wherever it was dropped, including on the side of a
 * casing, and the whole point of drawing the instrument rather than a dot is
 * that a stud-mounted accelerometer is visibly perpendicular to its face.
 */

import * as THREE from "three";

import type { TwinSensorPlacement, Vec3 } from "@/lib/digital-twin/types";
import { disposeObject } from "./dispose";

/** Marker geometry is built along local +Y — see `createSensorMarker`. */
const MARKER_AXIS = new THREE.Vector3(0, 1, 0);

function toVec3(vector: THREE.Vector3): Vec3 {
  return [vector.x, vector.y, vector.z];
}

/**
 * The rotation that stands a marker up on a surface.
 *
 * A degenerate normal falls back to +Y rather than producing a NaN quaternion,
 * which would silently remove the marker from the scene: three skips objects
 * whose matrix contains NaN, so the sensor would simply stop being drawn.
 */
export function quaternionForNormal(normal: THREE.Vector3): THREE.Quaternion {
  const direction =
    normal.lengthSq() > 1e-8 ? normal.clone().normalize() : MARKER_AXIS.clone();
  return new THREE.Quaternion().setFromUnitVectors(MARKER_AXIS, direction);
}

/**
 * Turn a ray hit on the machine into a placement.
 *
 * The face normal arrives in the hit *mesh's* local space, so it goes to world
 * through that mesh and then into the root's space. Taking it from mesh to root
 * in one step would be wrong as soon as the two sit under different parents,
 * which on a GLB they nearly always do.
 */
export function placementFromHit(
  root: THREE.Object3D,
  hit: THREE.Intersection
): TwinSensorPlacement | null {
  if (!hit.face) return null;

  const worldNormal = hit.face.normal
    .clone()
    .transformDirection(hit.object.matrixWorld)
    .normalize();

  const inverseRoot = new THREE.Matrix4().copy(root.matrixWorld).invert();

  return {
    point: toVec3(root.worldToLocal(hit.point.clone())),
    normal: toVec3(worldNormal.transformDirection(inverseRoot).normalize()),
  };
}

/** Stand an object — a marker holder, or the preview — on a placement. */
export function applyPlacement(
  object: THREE.Object3D,
  placement: TwinSensorPlacement
): void {
  object.position.set(placement.point[0], placement.point[1], placement.point[2]);
  object.quaternion.copy(
    quaternionForNormal(
      new THREE.Vector3(placement.normal[0], placement.normal[1], placement.normal[2])
    )
  );
}

export interface PlacementPreview {
  group: THREE.Group;
  /** Show the preview at a candidate placement. */
  moveTo: (placement: TwinSensorPlacement) => void;
  /** Hide it while the pointer is off the machine. */
  setVisible: (visible: boolean) => void;
  dispose: () => void;
}

/**
 * The ghost that follows the pointer during a drag.
 *
 * Deliberately not a copy of the real marker: a translucent stud over a contact
 * ring reads as "this is where it would go", where a second solid instrument
 * would read as a second sensor. It draws with `depthTest` off and a high
 * render order so it stays visible when the candidate point is on the far side
 * of the machine — a preview that disappears inside the casing is worse than no
 * preview, because the drag looks broken.
 */
export function createPlacementPreview(color: number): PlacementPreview {
  const group = new THREE.Group();
  group.renderOrder = 999;

  const ringMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.6,
    depthTest: false,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.16, 0.23, 32).rotateX(-Math.PI / 2),
    ringMaterial
  );
  ring.position.y = 0.004;
  group.add(ring);

  const studMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.34,
    depthTest: false,
  });
  const stud = new THREE.Mesh(
    new THREE.CylinderGeometry(0.1, 0.11, 0.26, 20),
    studMaterial
  );
  stud.position.y = 0.13;
  group.add(stud);

  group.traverse((child) => {
    child.renderOrder = 999;
  });

  return {
    group,
    moveTo: (placement) => {
      applyPlacement(group, placement);
      group.visible = true;
    },
    setVisible: (visible) => {
      group.visible = visible;
    },
    dispose: () => disposeObject(group),
  };
}

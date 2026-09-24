/**
 * Free sensor placement — the maths behind the drag.
 *
 * The interaction itself needs a browser, but the part that can be wrong in a
 * way nobody notices is the coordinate work: a normal taken from the wrong
 * space stands a sensor up at an angle, and a point stored in world space drifts
 * the next time the same machine is framed differently. Both are checked here,
 * against real three.js objects rather than stand-ins.
 */
import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  applyPlacement,
  createPlacementPreview,
  placementFromHit,
  quaternionForNormal,
} from "../scene/placement";
import type { TwinSensorPlacement } from "@/lib/digital-twin/types";

const UP = new THREE.Vector3(0, 1, 0);

/** Where a marker's own +Y ends up once the placement is applied. */
function markerAxisAfter(placement: TwinSensorPlacement): THREE.Vector3 {
  const holder = new THREE.Object3D();
  applyPlacement(holder, placement);
  holder.updateMatrixWorld(true);
  return UP.clone().applyQuaternion(holder.quaternion).normalize();
}

/**
 * A hit as the raycaster reports one.
 *
 * The face normal arrives in the hit *mesh's* local space — that is the detail
 * the coordinate work exists to handle, so the fixture reproduces it rather
 * than handing over a world-space normal that would make the tests pass for the
 * wrong reason.
 */
function hitOn(
  mesh: THREE.Mesh,
  worldPoint: THREE.Vector3,
  localNormal: THREE.Vector3
): THREE.Intersection {
  return {
    distance: 1,
    point: worldPoint,
    object: mesh,
    face: { a: 0, b: 1, c: 2, normal: localNormal, materialIndex: 0 },
  } as unknown as THREE.Intersection;
}

// ---------------------------------------------------------------------------
// Standing a marker on a surface
// ---------------------------------------------------------------------------

describe("quaternionForNormal", () => {
  it("leaves a marker upright on a horizontal face", () => {
    const axis = UP.clone().applyQuaternion(quaternionForNormal(new THREE.Vector3(0, 1, 0)));
    expect(axis.y).toBeCloseTo(1, 6);
  });

  it("lays a marker on its side on a vertical face", () => {
    // The whole reason the normal is stored: a sensor on the side of a casing
    // must point out of that casing, not at the sky.
    const axis = UP.clone().applyQuaternion(quaternionForNormal(new THREE.Vector3(0, 0, 1)));
    expect(axis.z).toBeCloseTo(1, 6);
    expect(axis.y).toBeCloseTo(0, 6);
  });

  it("handles a face pointing straight down", () => {
    // The antiparallel case: naive axis-angle maths produces a zero axis here
    // and a NaN quaternion, which would drop the marker out of the scene
    // entirely rather than draw it wrong.
    const axis = UP.clone().applyQuaternion(quaternionForNormal(new THREE.Vector3(0, -1, 0)));
    expect(axis.y).toBeCloseTo(-1, 6);
    expect(Number.isNaN(axis.x)).toBe(false);
  });

  it("falls back to upright rather than producing NaN for a zero normal", () => {
    const quaternion = quaternionForNormal(new THREE.Vector3(0, 0, 0));
    expect(Number.isNaN(quaternion.x)).toBe(false);
    expect(UP.clone().applyQuaternion(quaternion).y).toBeCloseTo(1, 6);
  });

  it("normalises a normal that did not arrive unit length", () => {
    const axis = UP.clone().applyQuaternion(quaternionForNormal(new THREE.Vector3(0, 0, 7)));
    expect(axis.length()).toBeCloseTo(1, 6);
    expect(axis.z).toBeCloseTo(1, 6);
  });
});

// ---------------------------------------------------------------------------
// World hit -> model-local placement
// ---------------------------------------------------------------------------

describe("placementFromHit", () => {
  function scene(rootTransform: (root: THREE.Object3D) => void) {
    const root = new THREE.Object3D();
    rootTransform(root);
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1));
    root.add(mesh);
    root.updateMatrixWorld(true);
    return { root, mesh };
  }

  it("records the point in the root's local space, not the world's", () => {
    // The root is moved and framed when a model loads. A world-space point
    // would land somewhere else the next time the same machine was opened.
    const { root, mesh } = scene((object) => object.position.set(10, 0, 0));

    const placement = placementFromHit(
      root,
      hitOn(mesh, new THREE.Vector3(10.5, 0, 0), new THREE.Vector3(1, 0, 0))
    );

    expect(placement).not.toBeNull();
    expect(placement!.point[0]).toBeCloseTo(0.5, 6);
  });

  it("survives the root being scaled", () => {
    const { root, mesh } = scene((object) => object.scale.setScalar(4));

    const placement = placementFromHit(
      root,
      hitOn(mesh, new THREE.Vector3(0, 2, 0), new THREE.Vector3(0, 1, 0))
    );

    expect(placement!.point[1]).toBeCloseTo(0.5, 6);
    expect(placement!.normal[1]).toBeCloseTo(1, 6);
  });

  it("takes the normal through the mesh's own transform", () => {
    // The face normal is in the *mesh's* local space. A mesh rotated inside the
    // model — which on a GLB is the normal case, not the exception — means the
    // two disagree, and reading the raw face normal would tilt the sensor.
    const root = new THREE.Object3D();
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1));
    mesh.rotation.z = Math.PI / 2; // local +X now points along world +Y
    root.add(mesh);
    root.updateMatrixWorld(true);

    const placement = placementFromHit(
      root,
      hitOn(mesh, new THREE.Vector3(0, 0.5, 0), new THREE.Vector3(1, 0, 0))
    );

    expect(placement!.normal[1]).toBeCloseTo(1, 6);
    expect(placement!.normal[0]).toBeCloseTo(0, 6);
  });

  it("returns a unit normal", () => {
    const { root, mesh } = scene((object) => object.scale.set(3, 3, 3));
    const placement = placementFromHit(
      root,
      hitOn(mesh, new THREE.Vector3(0, 1.5, 0), new THREE.Vector3(0, 2, 0))
    );

    const normal = new THREE.Vector3(...placement!.normal);
    expect(normal.length()).toBeCloseTo(1, 6);
  });

  it("refuses a hit with no face", () => {
    // Points, lines and sprites intersect without one. Better no placement than
    // a sensor standing on an arbitrary axis.
    const { root, mesh } = scene(() => {});
    const faceless = { distance: 1, point: new THREE.Vector3(), object: mesh };
    expect(placementFromHit(root, faceless as unknown as THREE.Intersection)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Round trip
// ---------------------------------------------------------------------------

describe("a placement, applied", () => {
  it("puts the marker back exactly where it was dropped", () => {
    const root = new THREE.Object3D();
    root.position.set(-2, 1, 4);
    root.rotation.y = Math.PI / 3;
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2));
    root.add(mesh);
    root.updateMatrixWorld(true);

    const dropPoint = mesh.localToWorld(new THREE.Vector3(0, 1, 0));
    const placement = placementFromHit(
      root,
      hitOn(mesh, dropPoint.clone(), new THREE.Vector3(0, 1, 0))
    )!;

    const holder = new THREE.Object3D();
    applyPlacement(holder, placement);
    root.add(holder);
    root.updateMatrixWorld(true);

    const landed = holder.getWorldPosition(new THREE.Vector3());
    expect(landed.distanceTo(dropPoint)).toBeCloseTo(0, 5);
  });

  it("stands the marker along the surface normal", () => {
    expect(markerAxisAfter({ point: [0, 0, 0], normal: [0, 0, 1] }).z).toBeCloseTo(1, 6);
    expect(markerAxisAfter({ point: [0, 0, 0], normal: [-1, 0, 0] }).x).toBeCloseTo(-1, 6);
  });
});

// ---------------------------------------------------------------------------
// The drag preview
// ---------------------------------------------------------------------------

describe("the placement preview", () => {
  it("starts hideable and moves onto a placement", () => {
    const preview = createPlacementPreview(0xff6b00);

    preview.setVisible(false);
    expect(preview.group.visible).toBe(false);

    preview.moveTo({ point: [1, 2, 3], normal: [0, 1, 0] });
    expect(preview.group.visible).toBe(true);
    expect(preview.group.position.toArray()).toEqual([1, 2, 3]);

    preview.dispose();
  });

  it("draws over the machine rather than inside it", () => {
    // A candidate point on the far side of the casing is still a valid drop; a
    // preview hidden by the geometry in front of it looks like a broken drag.
    const preview = createPlacementPreview(0xff6b00);

    const materials: THREE.Material[] = [];
    preview.group.traverse((child) => {
      const material = (child as THREE.Mesh).material;
      if (material && !Array.isArray(material)) materials.push(material);
    });

    expect(materials.length).toBeGreaterThan(0);
    expect(materials.every((material) => material.depthTest === false)).toBe(true);
    expect(preview.group.renderOrder).toBeGreaterThan(0);

    preview.dispose();
  });

  it("releases its geometry and detaches when disposed", () => {
    const parent = new THREE.Object3D();
    const preview = createPlacementPreview(0xff6b00);
    parent.add(preview.group);

    preview.dispose();

    expect(preview.group.parent).toBeNull();
  });
});

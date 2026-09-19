/**
 * Digital Twin — camera rig: orbit controls, framing and eased view moves.
 *
 * Framing fits the model's eight **bounding-box corners** to both fields of
 * view, rather than fitting its bounding sphere. A pump set is roughly nine
 * units long and three tall, so its sphere is nearly three times its height —
 * fitting that vertically would leave the machine a smudge in the middle of a
 * wide panel. Projecting the real corners frames it tightly from any angle, at
 * any aspect ratio, with no per-model tuning.
 */

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export const CAMERA_VIEWS = {
  iso: [1.05, 0.5, 1.4],
  front: [0, 0.12, 2.1],
  side: [2.1, 0.12, 0.02],
  top: [0.02, 2.2, 0.02],
} as const;

export type CameraViewId = keyof typeof CAMERA_VIEWS;

export const VIEW_TWEEN_MS = 650;
/** Headroom around the model, leaving room for the boundary label rows. */
const FRAMING_MARGIN = 1.18;

export interface Framing {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

export function framingFor(
  view: CameraViewId,
  box: THREE.Box3,
  aspect: number,
  fovDegrees: number
): Framing {
  const target = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());

  const vFov = (fovDegrees * Math.PI) / 180;
  const tanV = Math.tan(vFov / 2);
  const tanH = tanV * Math.max(aspect, 0.2);

  // `dir` runs from the target out toward the camera.
  const dir = new THREE.Vector3(...CAMERA_VIEWS[view]).normalize();
  const reference =
    Math.abs(dir.y) > 0.98 ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0);
  const right = new THREE.Vector3().crossVectors(reference, dir).normalize();
  const up = new THREE.Vector3().crossVectors(dir, right).normalize();

  const half = [size.x / 2, size.y / 2, size.z / 2];
  const corner = new THREE.Vector3();
  let distance = 0;

  for (let i = 0; i < 8; i += 1) {
    corner.set(
      (i & 1 ? 1 : -1) * half[0],
      (i & 2 ? 1 : -1) * half[1],
      (i & 4 ? 1 : -1) * half[2]
    );
    const depth = corner.dot(dir);
    const across = Math.abs(corner.dot(right)) * FRAMING_MARGIN;
    const above = Math.abs(corner.dot(up)) * FRAMING_MARGIN;
    distance = Math.max(distance, depth + across / tanH, depth + above / tanV);
  }

  return { position: dir.multiplyScalar(Math.max(distance, 0.1)).add(target), target };
}

/** Standard ease-in-out; the reference's 650 ms move uses the same shape. */
function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export class CameraRig {
  readonly controls: OrbitControls;
  private tween: {
    fromPosition: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toPosition: THREE.Vector3;
    toTarget: THREE.Vector3;
    elapsed: number;
  } | null = null;

  constructor(
    private camera: THREE.PerspectiveCamera,
    domElement: HTMLElement,
    onChange: () => void
  ) {
    const controls = new OrbitControls(camera, domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.075;
    controls.enablePan = true;
    controls.rotateSpeed = 0.85;
    controls.zoomSpeed = 0.9;
    // Stop just short of horizontal so the camera can never drop below the
    // shadow floor and look at the machine through it.
    controls.maxPolarAngle = Math.PI / 2 - 0.045;
    controls.minPolarAngle = 0.05;
    controls.addEventListener("change", onChange);
    this.controls = controls;

    // `pan-y` rather than `none`: on a phone a vertical swipe over the canvas
    // still scrolls the page, while a horizontal drag orbits the model — which
    // is the axis that matters. `none` turns the panel into a scroll trap.
    domElement.style.touchAction = "pan-y";
  }

  /** True while a view move is still running. */
  get animating(): boolean {
    return this.tween !== null;
  }

  /** Start a 650 ms eased move. */
  flyTo(framing: Framing) {
    this.tween = {
      fromPosition: this.camera.position.clone(),
      fromTarget: this.controls.target.clone(),
      toPosition: framing.position.clone(),
      toTarget: framing.target.clone(),
      elapsed: 0,
    };
  }

  /** Place the camera with no animation — first frame, and resizes. */
  snapTo(framing: Framing) {
    this.tween = null;
    this.camera.position.copy(framing.position);
    this.controls.target.copy(framing.target);
    this.controls.update();
  }

  /**
   * Advance the rig. Returns true while something is still moving, which is
   * what keeps the render loop awake.
   */
  update(deltaSeconds: number): boolean {
    let active = false;

    if (this.tween) {
      this.tween.elapsed += deltaSeconds * 1000;
      const t = Math.min(1, this.tween.elapsed / VIEW_TWEEN_MS);
      const eased = easeInOutCubic(t);
      this.camera.position.lerpVectors(this.tween.fromPosition, this.tween.toPosition, eased);
      this.controls.target.lerpVectors(this.tween.fromTarget, this.tween.toTarget, eased);
      if (t >= 1) this.tween = null;
      active = true;
    }

    // Damping only needs the loop while it is still settling.
    const before = this.camera.position.clone();
    this.controls.update();
    if (!active && before.distanceToSquared(this.camera.position) > 1e-10) active = true;

    return active;
  }

  dispose() {
    this.controls.dispose();
  }
}

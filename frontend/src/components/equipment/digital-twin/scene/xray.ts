/**
 * Digital Twin — x-ray mode.
 *
 * Fades casings, housings, covers and guards so the bearings and the shaft
 * inside become visible.
 *
 * Two things make this safe rather than a source of stuck-transparent bugs:
 *
 *  1. **Every material is cloned before it is touched.** A GLB routinely
 *     shares one material across many meshes, and glTF caches materials across
 *     loads of the same file — mutating one in place would fade unrelated
 *     geometry and would survive a model switch.
 *  2. **The original values are recorded and restored exactly.** `transparent`
 *     and `depthWrite` go back to what they were the moment the fade reaches
 *     zero, not merely to `true`/`true`, so a material that was already
 *     transparent stays transparent and an opaque one ends up genuinely opaque.
 */

import * as THREE from "three";

export const XRAY_OPACITY = 0.14;
const TWEEN_SECONDS = 0.34;

interface TrackedMaterial {
  mesh: THREE.Mesh;
  /** The material as it arrived, put back on dispose. */
  original: THREE.Material | THREE.Material[];
  clones: THREE.Material[];
  baseOpacity: number[];
  baseTransparent: boolean[];
  baseDepthWrite: boolean[];
}

function cloneMaterials(mesh: THREE.Mesh): TrackedMaterial {
  const original = mesh.material;
  const list = Array.isArray(original) ? original : [original];
  const clones = list.map((material) => material.clone());

  mesh.material = Array.isArray(original) ? clones : clones[0];

  return {
    mesh,
    original,
    clones,
    baseOpacity: clones.map((material) => material.opacity),
    baseTransparent: clones.map((material) => material.transparent),
    baseDepthWrite: clones.map((material) => (material as THREE.MeshStandardMaterial).depthWrite),
  };
}

export class XrayController {
  private tracked: TrackedMaterial[];
  private progress = 0;
  private target = 0;

  constructor(meshes: THREE.Mesh[]) {
    this.tracked = meshes.map(cloneMaterials);
  }

  get enabled(): boolean {
    return this.target > 0.5;
  }

  /** True while the fade is still moving, so the caller keeps the loop alive. */
  get animating(): boolean {
    return Math.abs(this.progress - this.target) > 1e-4;
  }

  setEnabled(on: boolean) {
    this.target = on ? 1 : 0;
  }

  /** Jump straight to the current target — used when re-applying after a swap. */
  snap() {
    this.progress = this.target;
    this.apply();
  }

  update(deltaSeconds: number): boolean {
    if (!this.animating) return false;
    const step = deltaSeconds / TWEEN_SECONDS;
    this.progress =
      this.progress < this.target
        ? Math.min(this.target, this.progress + step)
        : Math.max(this.target, this.progress - step);
    this.apply();
    return true;
  }

  private apply() {
    const t = this.progress;
    this.tracked.forEach((entry) => {
      entry.clones.forEach((material, index) => {
        const base = entry.baseOpacity[index];
        material.opacity = base + (XRAY_OPACITY - base) * t;

        if (t <= 1e-4) {
          // Fully restored: hand back the exact flags the material had, so
          // nothing is left transparent or depth-write-disabled.
          material.opacity = base;
          material.transparent = entry.baseTransparent[index];
          (material as THREE.MeshStandardMaterial).depthWrite =
            entry.baseDepthWrite[index];
        } else {
          material.transparent = true;
          (material as THREE.MeshStandardMaterial).depthWrite = false;
        }
        material.needsUpdate = true;
      });

      // A faded shell casting a solid shadow gives the trick away.
      entry.mesh.castShadow = t <= 0.5;
    });
  }

  /** Put the original materials back and release every clone. */
  dispose() {
    this.tracked.forEach((entry) => {
      entry.mesh.material = entry.original;
      entry.mesh.castShadow = true;
      entry.clones.forEach((material) => material.dispose());
    });
    this.tracked = [];
  }
}

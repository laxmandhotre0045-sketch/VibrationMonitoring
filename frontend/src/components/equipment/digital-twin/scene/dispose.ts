/**
 * Digital Twin — GPU resource teardown.
 *
 * The twin rebuilds whenever the configuration changes and the component
 * mounts and unmounts as the user moves through the setup flow, so anything
 * not released here leaks once per change for as long as the tab is open.
 *
 * `renderer.info.memory` is the check that matters: geometry and texture
 * counts must come back to zero after teardown.
 */

import * as THREE from "three";

function disposeMaterial(material: THREE.Material) {
  // Any slot on a material can own a texture. Walking the object rather than
  // naming `map`, `normalMap`, ... means a material from a GLB we have never
  // seen still gets fully released.
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) value.dispose();
  }
  material.dispose();
}

/**
 * Release every geometry, material and texture under `root`, then detach it.
 *
 * Safe on an object that was never added to a scene, and on null.
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

/** Empty a scene of its children, releasing each. */
export function disposeSceneContents(scene: THREE.Scene) {
  [...scene.children].forEach(disposeObject);
  scene.clear();
}

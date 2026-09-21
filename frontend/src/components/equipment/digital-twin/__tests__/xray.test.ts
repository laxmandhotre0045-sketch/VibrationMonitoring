import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { XrayController, XRAY_OPACITY } from "../scene/xray";

function mesh(material: THREE.Material): THREE.Mesh {
  return new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), material);
}

/** Drive the tween to completion. */
function settle(controller: XrayController) {
  for (let i = 0; i < 200 && controller.animating; i += 1) controller.update(0.016);
}

describe("XrayController", () => {
  it("clones materials instead of mutating the originals", () => {
    const original = new THREE.MeshStandardMaterial({ color: 0x336699 });
    const box = mesh(original);
    const controller = new XrayController([box]);

    expect(box.material).not.toBe(original);

    controller.setEnabled(true);
    settle(controller);

    // The whole point: the shared original is untouched.
    expect(original.opacity).toBe(1);
    expect(original.transparent).toBe(false);
    controller.dispose();
  });

  it("gives two meshes sharing one material separate clones", () => {
    // A GLB routinely shares one material across many meshes, and glTF caches
    // materials across loads of the same file.
    const shared = new THREE.MeshStandardMaterial();
    const a = mesh(shared);
    const b = mesh(shared);
    const controller = new XrayController([a, b]);

    expect(a.material).not.toBe(b.material);
    expect(a.material).not.toBe(shared);
    expect(b.material).not.toBe(shared);
    controller.dispose();
  });

  it("fades to the x-ray opacity with depth writing off", () => {
    const box = mesh(new THREE.MeshStandardMaterial());
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    settle(controller);

    const material = box.material as THREE.MeshStandardMaterial;
    expect(material.opacity).toBeCloseTo(XRAY_OPACITY, 5);
    expect(material.transparent).toBe(true);
    expect(material.depthWrite).toBe(false);
    // A faded shell casting a solid shadow would give the trick away.
    expect(box.castShadow).toBe(false);
    controller.dispose();
  });

  // The acceptance criterion: nothing may be left stuck transparent.
  it("restores an opaque material exactly when switched off", () => {
    const box = mesh(new THREE.MeshStandardMaterial());
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    settle(controller);
    controller.setEnabled(false);
    settle(controller);

    const material = box.material as THREE.MeshStandardMaterial;
    expect(material.opacity).toBe(1);
    expect(material.transparent).toBe(false);
    expect(material.depthWrite).toBe(true);
    expect(box.castShadow).toBe(true);
    controller.dispose();
  });

  it("restores an already-transparent material to its own values, not to opaque", () => {
    // Restoring to `transparent = false` would be just as wrong as leaving it
    // faded — glass and guards are legitimately translucent to begin with.
    const original = new THREE.MeshStandardMaterial({
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    });
    const box = mesh(original);
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    settle(controller);
    controller.setEnabled(false);
    settle(controller);

    const material = box.material as THREE.MeshStandardMaterial;
    expect(material.opacity).toBeCloseTo(0.5, 5);
    expect(material.transparent).toBe(true);
    expect(material.depthWrite).toBe(false);
    controller.dispose();
  });

  it("does not drift over repeated toggles", () => {
    const box = mesh(new THREE.MeshStandardMaterial());
    const controller = new XrayController([box]);

    for (let i = 0; i < 12; i += 1) {
      controller.setEnabled(true);
      settle(controller);
      controller.setEnabled(false);
      settle(controller);
    }

    expect((box.material as THREE.MeshStandardMaterial).opacity).toBe(1);
    expect((box.material as THREE.MeshStandardMaterial).transparent).toBe(false);
    controller.dispose();
  });

  it("survives a toggle interrupted half way", () => {
    const box = mesh(new THREE.MeshStandardMaterial());
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    controller.update(0.1); // part way in
    controller.setEnabled(false);
    settle(controller);

    expect((box.material as THREE.MeshStandardMaterial).opacity).toBe(1);
    expect((box.material as THREE.MeshStandardMaterial).transparent).toBe(false);
    controller.dispose();
  });

  it("handles multi-material meshes", () => {
    const materials = [
      new THREE.MeshStandardMaterial(),
      new THREE.MeshStandardMaterial({ transparent: true, opacity: 0.8 }),
    ];
    const box = mesh(materials[0]);
    box.material = materials;
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    settle(controller);
    (box.material as THREE.Material[]).forEach((material) => {
      expect(material.opacity).toBeCloseTo(XRAY_OPACITY, 5);
    });

    controller.setEnabled(false);
    settle(controller);
    const restored = box.material as THREE.Material[];
    expect(restored[0].opacity).toBe(1);
    expect(restored[0].transparent).toBe(false);
    expect(restored[1].opacity).toBeCloseTo(0.8, 5);
    expect(restored[1].transparent).toBe(true);
    controller.dispose();
  });

  it("snap() applies the target with no tween", () => {
    const box = mesh(new THREE.MeshStandardMaterial());
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    controller.snap();

    expect(controller.animating).toBe(false);
    expect((box.material as THREE.MeshStandardMaterial).opacity).toBeCloseTo(XRAY_OPACITY, 5);
    controller.dispose();
  });

  it("puts the original material back on dispose, even mid-fade", () => {
    // This is what protects a machine-type switch: the model is torn down
    // while x-ray is still on, and nothing may be left altered.
    const original = new THREE.MeshStandardMaterial();
    const box = mesh(original);
    const controller = new XrayController([box]);

    controller.setEnabled(true);
    controller.update(0.1);
    controller.dispose();

    expect(box.material).toBe(original);
    expect(original.opacity).toBe(1);
    expect(original.transparent).toBe(false);
    expect(box.castShadow).toBe(true);
  });

  it("reports animating only while the fade is moving", () => {
    const controller = new XrayController([mesh(new THREE.MeshStandardMaterial())]);
    expect(controller.animating).toBe(false);

    controller.setEnabled(true);
    expect(controller.animating).toBe(true);
    settle(controller);
    expect(controller.animating).toBe(false);
    expect(controller.enabled).toBe(true);
    controller.dispose();
  });

  it("copes with an empty x-ray layer", () => {
    const controller = new XrayController([]);
    controller.setEnabled(true);
    settle(controller);
    expect(() => controller.dispose()).not.toThrow();
  });
});

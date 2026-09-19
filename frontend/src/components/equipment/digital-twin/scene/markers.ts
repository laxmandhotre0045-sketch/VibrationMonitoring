/**
 * Digital Twin — sensor and bearing markers.
 *
 * A sensor marker is a small accelerometer: hex base, steel body, coloured cap
 * and a short cable. It is built pointing along its own local **+Y**, so
 * parenting it to an anchor node — whose local +Y is the measurement axis by
 * convention — orients it with no maths at the call site. That is what makes
 * horizontal, vertical and axial visibly different on the model itself rather
 * than only in a label.
 */

import * as THREE from "three";
import type { SensorStatus } from "@/lib/digital-twin/types";

const STATUS_COLOR: Record<SensorStatus, number> = {
  ok: 0xff6b00,
  alert: 0xf5a623,
  danger: 0xef4444,
};

/** Cap colour. No status means "configured, not yet graded" — brand orange. */
export function markerColor(status?: SensorStatus): number {
  return status ? STATUS_COLOR[status] : 0xff6b00;
}

export const UNMAPPED_COLOR = 0x94a3b8;
const STEEL = 0xc3cad6;
const BASE_METAL = 0x7e8a9b;
const CABLE = 0x3a4250;

export interface SensorMarker {
  group: THREE.Group;
  /** Pulses on highlight. */
  setHighlighted: (on: boolean) => void;
}

/**
 * One accelerometer, standing on the surface with its axis along local +Y.
 *
 * Everything is sized in model units where 1 unit ≈ 100 mm, so the body is
 * about the 25 mm a real stud-mounted accelerometer would be.
 */
export function createSensorMarker(color: number): SensorMarker {
  const group = new THREE.Group();

  const capMaterial = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.35,
    metalness: 0.1,
  });
  const steelMaterial = new THREE.MeshStandardMaterial({
    color: STEEL,
    roughness: 0.28,
    metalness: 0.85,
  });
  const baseMaterial = new THREE.MeshStandardMaterial({
    color: BASE_METAL,
    roughness: 0.42,
    metalness: 0.7,
  });

  // Hex base — 6 radial segments reads as a spanner flat, which is what sells
  // it as an instrument rather than a dot.
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.135, 0.145, 0.05, 6), baseMaterial);
  base.position.y = 0.025;
  group.add(base);

  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.095, 0.105, 0.16, 24), steelMaterial);
  body.position.y = 0.13;
  group.add(body);

  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.082, 0.098, 0.06, 24), capMaterial);
  cap.position.y = 0.24;
  group.add(cap);

  // A short whip of cable leaving the top and falling away, so the marker has
  // an obvious "up" even end-on.
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, 0.27, 0),
    new THREE.Vector3(0.02, 0.35, 0.04),
    new THREE.Vector3(0.1, 0.39, 0.12),
    new THREE.Vector3(0.24, 0.35, 0.2),
  ]);
  const cable = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 14, 0.018, 6, false),
    new THREE.MeshStandardMaterial({ color: CABLE, roughness: 0.75, metalness: 0.05 })
  );
  group.add(cable);

  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.castShadow = true;
      mesh.receiveShadow = true;
    }
  });

  // A translucent halo, hidden until highlighted — gives the "pulse" something
  // to grow without resizing the instrument itself.
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(0.3, 18, 12),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false })
  );
  halo.position.y = 0.16;
  halo.visible = false;
  group.add(halo);

  return {
    group,
    setHighlighted: (on: boolean) => {
      halo.visible = on;
      capMaterial.emissive.setHex(on ? color : 0x000000);
      capMaterial.emissiveIntensity = on ? 0.55 : 0;
    },
  };
}

export interface BearingMarker {
  group: THREE.Group;
  setHighlighted: (on: boolean) => void;
}

/**
 * A bearing ring, drawn around the shaft at a `BRG_*` anchor.
 *
 * Configured bearings get an amber emissive tint, which is what makes them
 * legible through a faded casing in x-ray. An unconfigured position is a faint
 * grey outline — the machine has the position, the form has not filled it in,
 * and the twin must not imply a part that is not there.
 */
export function createBearingMarker(radius: number, configured: boolean): BearingMarker {
  const group = new THREE.Group();

  const material = new THREE.MeshStandardMaterial({
    color: configured ? 0xf5a623 : 0xbcc7d6,
    roughness: configured ? 0.3 : 0.6,
    metalness: configured ? 0.75 : 0.2,
    transparent: !configured,
    opacity: configured ? 1 : 0.35,
    emissive: new THREE.Color(configured ? 0x7a4c00 : 0x000000),
    emissiveIntensity: configured ? 0.45 : 0,
  });

  const ring = new THREE.Mesh(
    // Torus is built in the XY plane; stand it up around the shaft (local X).
    new THREE.TorusGeometry(radius, radius * 0.26, 14, 40).rotateY(Math.PI / 2),
    material
  );
  ring.castShadow = configured;
  group.add(ring);

  if (configured) {
    // Rolling elements, so a configured bearing reads as a bearing under x-ray
    // rather than as a plain band.
    const elementGeometry = new THREE.SphereGeometry(radius * 0.19, 10, 8);
    const elementMaterial = new THREE.MeshStandardMaterial({
      color: 0xe8ecf2,
      roughness: 0.18,
      metalness: 0.95,
    });
    const count = 10;
    const elements = new THREE.InstancedMesh(elementGeometry, elementMaterial, count);
    const matrix = new THREE.Matrix4();
    for (let i = 0; i < count; i += 1) {
      const angle = (i / count) * Math.PI * 2;
      matrix.setPosition(0, Math.cos(angle) * radius, Math.sin(angle) * radius);
      elements.setMatrixAt(i, matrix);
    }
    elements.instanceMatrix.needsUpdate = true;
    group.add(elements);
  }

  return {
    group,
    setHighlighted: (on: boolean) => {
      material.emissive.setHex(on ? 0xff6b00 : configured ? 0x7a4c00 : 0x000000);
      material.emissiveIntensity = on ? 0.9 : configured ? 0.45 : 0;
    },
  };
}

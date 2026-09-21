/**
 * Digital Twin — GLB model source.
 *
 * Loads `public/models/{type}.glb`, then finds its anchors *by node name*
 * rather than by baked-in coordinates, so re-exporting a model with parts
 * moved does not require a code change.
 *
 * Naming contract (see `docs/digital-twin-models.md`):
 *   CH1…CHn or CH_<LOCATION>_<AXIS>  sensor mounting empties, local +Y = axis
 *   BRG_<LOCATION>                   bearing centres
 *   …casing… …housing… …cover… …guard…   the x-ray layer
 *   ROTOR                            everything that spins, local X on the shaft
 */

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { applyStandardMaterialSettings } from "./renderer";
import {
  BEARING_NODE_PATTERN,
  ROTOR_NODE_PATTERN,
  SENSOR_NODE_PATTERN,
  XRAY_NAME_PATTERN,
  sensorNodeName,
  anchorSlug,
} from "@/lib/digital-twin/machine-type-map";
import type { TwinModelSource } from "@/lib/digital-twin/types";

/** Models are authored at 1 unit = 100 mm, matching the procedural registry. */
const MIN_REASONABLE_EXTENT = 1;
const MAX_REASONABLE_EXTENT = 60;
const NORMALISED_EXTENT = 9;

let loader: GLTFLoader | null = null;

function getLoader(): GLTFLoader {
  if (!loader) {
    loader = new GLTFLoader();
    // Meshopt keeps the GLBs under the 2 MB budget. The decoder is a tiny wasm
    // shim that ships with three; wiring it here means every load gets it.
    loader.setMeshoptDecoder(MeshoptDecoder);
  }
  return loader;
}

/**
 * The canonical anchor name for a `CH<n>` empty.
 *
 * glTF custom properties arrive on `userData`, so an artist can keep the
 * numbered names the spec calls for and still tell us which mounting point and
 * axis each one is.
 */
function canonicalSensorName(node: THREE.Object3D): string | null {
  const extras = node.userData as { location?: string; axis?: string; anchor?: string };
  if (typeof extras.anchor === "string" && extras.anchor.length > 0) return extras.anchor;
  if (typeof extras.location === "string" && typeof extras.axis === "string") {
    return sensorNodeName(anchorSlug(extras.location), extras.axis);
  }
  return null;
}

/** Walk the loaded scene once, collecting everything the viewer needs. */
function scanNodes(root: THREE.Object3D): Omit<TwinModelSource, "kind" | "schematic"> {
  const sensorAnchors = new Map<string, THREE.Object3D>();
  const bearingAnchors = new Map<string, THREE.Object3D>();
  const xrayMeshes: THREE.Mesh[] = [];
  let rotor: THREE.Object3D | null = null;

  root.traverse((node) => {
    const name = node.name ?? "";

    if (ROTOR_NODE_PATTERN.test(name)) {
      rotor = node;
      return;
    }

    if (BEARING_NODE_PATTERN.test(name)) {
      bearingAnchors.set(name.toUpperCase(), node);
      return;
    }

    if (SENSOR_NODE_PATTERN.test(name)) {
      // Register under its own name and, when the extras say what it is, under
      // the canonical name the adapter asks for.
      sensorAnchors.set(name.toUpperCase(), node);
      const canonical = canonicalSensorName(node);
      if (canonical) sensorAnchors.set(canonical.toUpperCase(), node);
      return;
    }

    const mesh = node as THREE.Mesh;
    if (mesh.isMesh && (XRAY_NAME_PATTERN.test(name) || node.userData.xray === true)) {
      mesh.userData.xray = true;
      xrayMeshes.push(mesh);
    }
  });

  return { root, sensorAnchors, bearingAnchors, xrayMeshes, rotor };
}

/**
 * Bring a model onto the scene's scale and sit it on y = 0.
 *
 * A correctly authored model is left alone. One exported in metres (or
 * millimetres) would otherwise make the markers look absurd and break camera
 * framing, so an obviously wrong scale is corrected and reported.
 */
function normalise(root: THREE.Object3D): void {
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const extent = Math.max(size.x, size.y, size.z);
  if (!Number.isFinite(extent) || extent <= 0) return;

  if (extent < MIN_REASONABLE_EXTENT || extent > MAX_REASONABLE_EXTENT) {
    const scale = NORMALISED_EXTENT / extent;
    root.scale.multiplyScalar(scale);
    root.updateMatrixWorld(true);
    if (import.meta.env.DEV) {
      console.warn(
        `[digital-twin] "${root.name}" is ${extent.toFixed(2)} units across; ` +
          `models should be authored at 1 unit = 100 mm. Scaled by ${scale.toFixed(3)}.`
      );
    }
  }

  const grounded = new THREE.Box3().setFromObject(root);
  root.position.y -= grounded.min.y;
}

/** True when the URL has a model behind it. Cached — 404s should cost once. */
const availability = new Map<string, Promise<boolean>>();

export function isModelAvailable(url: string): Promise<boolean> {
  const cached = availability.get(url);
  if (cached) return cached;

  const probe = fetch(url, { method: "HEAD" })
    .then((response) => response.ok)
    .catch(() => false);
  availability.set(url, probe);
  return probe;
}

export async function loadGlbSource(
  url: string,
  signal?: AbortSignal
): Promise<TwinModelSource> {
  const gltf = await getLoader().loadAsync(url);
  if (signal?.aborted) {
    // The viewer moved on while this was in flight. Release it rather than
    // handing back a model nobody will mount (and therefore nobody disposes).
    gltf.scene.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (mesh.isMesh) mesh.geometry?.dispose();
    });
    throw new DOMException("Aborted", "AbortError");
  }

  const root = gltf.scene;
  root.name = root.name || url;
  normalise(root);
  applyStandardMaterialSettings(root);

  return { ...scanNodes(root), kind: "glb", schematic: false };
}

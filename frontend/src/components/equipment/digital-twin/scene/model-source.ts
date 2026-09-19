/**
 * Digital Twin — one entry point for getting a model.
 *
 * Prefers `public/models/{type}.glb`; falls back to the procedural registry
 * when the file is not there yet or fails to load. Both return the same
 * `TwinModelSource`, so the viewer has a single code path.
 *
 * The fallback is not a degraded placeholder — it gets the same studio
 * lighting, anchors, labels, x-ray and highlighting as a GLB. A machine type
 * without a GLB is less detailed, never less usable.
 */

import { glbUrlFor, proceduralModelIdFor } from "@/lib/digital-twin/machine-type-map";
import type { MachineTypeId, TwinModelSource } from "@/lib/digital-twin/types";
import { isModelAvailable, loadGlbSource } from "./gltf-source";
import { buildProceduralSource } from "./procedural-source";

export interface LoadedModel extends TwinModelSource {
  /** Set when a GLB existed but could not be used, for the UI to explain. */
  loadError?: string;
}

export async function loadModelSource(
  typeId: MachineTypeId,
  signal?: AbortSignal
): Promise<LoadedModel> {
  const url = glbUrlFor(typeId);
  const proceduralId = proceduralModelIdFor(typeId);

  if (!url) return buildProceduralSource(proceduralId);

  // HEAD first: with no GLBs authored yet every type would otherwise push a
  // failed GLTFLoader request through the console on each switch. The result
  // is cached per URL, so this costs one round trip per model per session.
  const available = await isModelAvailable(url);
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (!available) return buildProceduralSource(proceduralId);

  try {
    return await loadGlbSource(url, signal);
  } catch (error) {
    if ((error as DOMException)?.name === "AbortError") throw error;
    // A present-but-broken GLB is worth saying out loud, unlike an absent one.
    return {
      ...buildProceduralSource(proceduralId),
      loadError:
        error instanceof Error ? error.message : "The 3D model could not be loaded.",
    };
  }
}

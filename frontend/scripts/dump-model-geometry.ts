/**
 * Dump every procedural machine model as JSON, for the preview renderer.
 *
 * The geometry lives in TypeScript because the viewer builds from it at
 * runtime. The preview renderer is Python. Rather than describe each machine
 * twice — which guarantees the previews drift from what the viewer actually
 * draws — this exports the real specs and the renderer reads them.
 *
 * Run through vite-node, which resolves the "@/" alias and the TS:
 *   npx vite-node scripts/dump-model-geometry.ts
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  GENERIC_MACHINE_MODEL,
  MACHINE_MODELS,
  modelBounds,
} from "../src/lib/digital-twin/machine-registry";
import { CAMERA_VIEWS } from "../src/components/equipment/digital-twin/scene/camera-rig";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "model-geometry.json");

// GENERIC is exported on its own — it is the fallback, not a listed model —
// but it still needs a preview, so it joins the set here.
const ALL = MACHINE_MODELS.some((m) => m.id === GENERIC_MACHINE_MODEL.id)
  ? MACHINE_MODELS
  : [...MACHINE_MODELS, GENERIC_MACHINE_MODEL];

const models = ALL.map((model) => ({
  id: model.id,
  label: model.label,
  schematic: model.schematic === true,
  bounds: modelBounds(model),
  components: model.components.map((c) => ({
    id: c.id,
    shape: c.shape,
    position: c.position,
    size: c.size,
    axis: c.axis ?? "x",
    rotation: c.rotation ?? null,
    tone: c.tone ?? "body",
  })),
  // Drawn on the render so a preview shows where the instruments go, the same
  // way the live twin does.
  bearingAnchors: model.bearingAnchors.map((a) => ({ id: a.id, position: a.position, radius: a.radius })),
  sensorAnchors: model.sensorAnchors.map((a) => ({
    id: a.id,
    axisPoint: a.axisPoint,
    radius: a.radius,
    static: a.static === true,
  })),
}));

// The renderer frames each model the way the viewer does on load, so the still
// and the model that replaces it sit in the same place.
const payload = { isoDirection: CAMERA_VIEWS.iso, models };

writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf8");
console.log(`${models.length} models -> ${OUT}`);
for (const m of models) {
  console.log(`  ${m.id.padEnd(11)} ${String(m.components.length).padStart(3)} parts`);
}

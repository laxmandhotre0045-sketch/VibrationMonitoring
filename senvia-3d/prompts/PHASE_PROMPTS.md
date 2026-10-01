# Prompts to paste into Claude Code (one phase at a time)

Before each phase: open Claude Code in the senvia-3d folder. It reads CLAUDE.md automatically.

## Phase 0 — orient
Read CLAUDE.md and docs/SOLUTION_C.md. Run `python tools/run_checks.py` and `python tools/export_models.py --ids es mill`.
Tell me the results and list anything that does not work on my machine. Do not change code yet.

## Phase 1 — extract the library
Split legacy/senvia_3d_library.html into ES modules under web/core/ (materials, geometry, parts, machines/<id>.js,
components/<id>.js, rules/, register.js) plus web/playground/index.html that imports them and looks and behaves exactly
like the legacy page. Keep window.__lib / window.__obj hooks. Update tools/export_models.py and tools/run_checks.py to
load the playground page. Done when run_checks.py reports failures: 0 and exports match the legacy file (same point
counts, bearing sizes, draw calls within 5 %). Work in small commits.

## Phase 2 — export and JSON
Export all 94 models. Add to model JSON: design_rotation, direction_sensitive, internals list, guard/flow/sensor node
names, and a fault_orders placeholder per bearing. Add GLB compression (gltf-transform CLI or Draco) with a size report;
target <= 3 MB per machine, <= 1 MB per component. Write assets/models/catalog.json. Add a pytest that validates every
model.json against a JSON schema in docs/model.schema.json.

## Phase 3 — viewer
Create web/viewer/senvia-viewer.js: an ES module that loads model.json + model.glb (GLTFLoader) and implements the API
in docs/SOLUTION_C.md: rotation from `ratio` × rpm, See-inside (INTERNAL_ nodes + transparent casings), flow, sensors,
guards, point markers with status colours (ISO 20816 zones), pointClick event, reverse-rotation warning.
Add web/viewer/demo.html that lists catalog.json and opens any model. Must run on a mid-range phone.

## Phase 4 — backend (Python)
In our Python backend (<framework>), add the tables in docs/SOLUTION_C.md with migrations, and the API endpoints.
Serve GLB/JSON through signed URLs. Add tests. Do not change existing Senvia tables except by adding foreign keys.

## Phase 5 — live link
Publish point status and running speed per asset on the WebSocket (from our existing measurement pipeline).
In the viewer, call setRunning and setPointStatus from the socket. Map alarm fault types (BPFO, BPFI, unbalance,
misalignment, looseness, gear mesh) to parts: bearing ids, shafts, couplings, gears. Add an end-to-end test with a
simulated sensor feed.

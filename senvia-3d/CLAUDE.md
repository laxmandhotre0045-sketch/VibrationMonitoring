# Senvia 3D Asset System

3D equipment library for the Senvia condition-monitoring platform (Sensovibe Reliability).
Design: docs/SOLUTION_C.md (full version: docs/Senvia_3D_Solution_C_Design.docx).

## Stack
- Backend and tools: **Python** (Senvia backend framework: FILL IN — FastAPI or Django).
- 3D runs in the browser, so the model library and the viewer are **JavaScript + Three.js r128**.
  Python never draws 3D; it builds, checks, stores and serves GLB + JSON files and live data.
- Build/QA tools are Python + Playwright (headless Chromium drives the JS library).

## Layout
- legacy/senvia_3d_library.html — current working library (48 machines, 46 components). Source of truth until Phase 1 is done.
- web/core/ — (Phase 1) library split into JS modules. web/viewer/ — (Phase 3) runtime viewer.
- tools/export_models.py — builds GLB + JSON per model into assets/models/<MODEL_ID>/<version>/.
- tools/run_checks.py — bug-hunt CI gate (checks/bug_hunt.js). Must exit 0 before any release.
- backend/ — (Phase 4) Python package: catalog, assets, point-to-sensor mapping, live status API.
- ../frontend/public/senvia-3d/ — the copy Senvia serves, built from legacy/ by
  tools/build_web_library.py (vendored three r128 + Barlow, browser downloads, host bridge).
  Never edit it by hand: change legacy/ or the build script and rebuild.
- assets/ — build output, never commit.

## Commands
- pip install -r requirements.txt && playwright install chromium
- python tools/run_checks.py            # all 94 models; expect "failures: 0"
- python tools/export_models.py --ids es mill   # or no --ids for all
- python tools/build_web_library.py     # builds frontend/public/senvia-3d/library.html
- python tools/check_web_library.py     # gate for that built copy; expect "failures: 0"

## Rules (do not break)
- Keep model IDs (EQ-xxx-nnn / CO-xxx-nnn), names, RAL paint colours and ISO point numbering
  (MP_01 = driver NDE, then along the train). Points never renumber silently: bump the major version.
- GLB node names: MP_nn_LABEL, ROT_nn, INTERNAL_n, FLOW_n, SENSOR_n, GUARD_n. Units metres, shaft along X, Y up.
- Physics: vanes trail rotation, gear meshes opposite, belts same direction, every rotor on a shaft,
  bearings sized from the journal (OD 1.8 x bore). Direction-sensitive machines show a reverse-rotation warning.
- Phone budget per machine: <= 250 draw calls, <= 60k triangles (every feature on).
- By-design items are listed in tools/run_checks.py BY_DESIGN. Do not add to that list without asking.
- Customer data (assets, sensors, readings) stays in the Senvia database; the viewer calls no external service.
- After any change to the library: run tools/run_checks.py and fix every failure before finishing.

# Solution C — Python edition (summary for Claude Code)

## Who does what
| Part | Language | Job |
|---|---|---|
| Model library (web/core) | JavaScript + Three.js | Builds every machine procedurally (from legacy/senvia_3d_library.html) |
| Export + checks (tools/) | Python + Playwright | Runs the library headless, checks it, writes GLB + JSON |
| Asset store | files | assets/models/<MODEL_ID>/<version>/model.glb + model.json, catalog.json; S3/MinIO/Azure in production |
| Backend (backend/) | Python (FastAPI or Django) | Catalog, customer assets, point-to-sensor mapping, bearing data, live status, WebSocket |
| Viewer (web/viewer) | JavaScript ES module | Loads GLB + JSON, rotation, See-inside, flow, sensors, point colours; served as a static file by the Python app |

## Model JSON (written by tools/export_models.py)
model_id, library_id, version, name, industry, drive, kind, paint[], parts,
points[{id, label, measure, position}], rotating[{node, axis, centre, ratio, internal}],
bearings[{id, type, bore_mm, od_mm, width_mm, position, designation}], flow_paths, stats{draw_calls, triangles, size_kb}.
Add in Phase 2: design_rotation, direction_sensitive, internals list, fault_orders per bearing.

## Backend tables (SQLAlchemy or Django models)
model_catalog, model_version, asset (pinned model_version), asset_point (mp_id -> sensor_id, channel, direction),
asset_bearing (designation, fault_orders), asset_photo, point_status (ISO 20816 zone), alarm (fault_type -> part).

## Backend API (suggested)
GET /api/3d/catalog · GET /api/3d/models/{model_id}/{version} (signed URLs to GLB/JSON)
GET/POST /api/assets/{id}/points · GET/POST /api/assets/{id}/bearings
WS /ws/assets/{id}/status  -> {"mp":"MP_03","level":"alert","value":7.1,"unit":"mm/s","rpm":1480}

## Viewer API (JavaScript, used from Django/Jinja templates, Dash, Streamlit or any web page)
load(modelId, version) · bindAsset(asset) · setRunning(rpm) · setDirection(dir) · setSeeInside/Flow/Sensors/Guards(bool)
setPointStatus(mp, status) · focusPoint(mp) · highlightPart(node) · screenshot() · on('pointClick'|'ready'|'error', cb)

## Embedding in a Python web app
- Django/Flask/FastAPI templates: <div id="v"></div><script type="module" src="/static/senvia-viewer.js"></script>
- Dash: wrap as a small custom component, or use an html.Iframe pointing to a viewer route.
- Streamlit: streamlit.components.v1.html(...) with the viewer script.
- Mobile: the same viewer inside a WebView.

## Phases
1 Extract library into web/core (behaviour identical: run_checks.py still 0 failures)
2 Export all 94 models; extend JSON fields; compress GLB (gltf-transform or Draco)
3 Viewer module + demo page reading assets/models
4 Backend tables + API in the Senvia Python backend
5 Live link: status WebSocket -> viewer point colours, alarms highlight parts
6 Pilot on one customer site

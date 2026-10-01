"""Check the built Senvia copy of the 3D library — the file we actually ship.

``run_checks.py`` proves the kit's own library is sound. This proves the copy in
``frontend/public/senvia-3d/`` survived the build: the vendored three.js loads,
the toolbar is whole, the export buttons are reachable without the Claude
downloads capability, the host bridge answers, and — the reason this file
exists — shafts turn about their own axis instead of swinging around the
machine.

That last one is worth a check of its own. A three.js Group rotates about its
own origin. A shaft mesh sitting at the machine's shaft height inside a group
whose origin is on the floor does not spin: it orbits, on a radius equal to that
height, and swings visibly outside the casing. The kit avoids this with
``pivotSpinners``, which moves each spinning group's origin onto its shaft axis
and compensates the children. The test below turns every spinner half a turn and
measures how far each part's world centre moved. A part turning in place barely
moves. A part that orbits moves by twice its offset.

Parts that orbit *by design* — planet gears riding a carrier, a conrod on a
crank — are listed in ORBITAL and excluded, because for them the movement is the
physics, not a bug.

Serves the folder over HTTP rather than file://, so the page runs on the same
origin it will run on in the product and the bridge's origin checks behave.

Run: python tools/check_web_library.py
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

KIT = Path(__file__).resolve().parents[1]
WEB = KIT.parent / "frontend" / "public" / "senvia-3d"

# Machines checked for rotation. The first is the one in the product
# screenshots; the rest cover a gear train, a belt drive, a vertical machine and
# a crank, which is where an origin mistake shows up worst.
ROTATION_MODELS = ["es", "gb", "beltfan", "vtp", "recip", "mill", "fan", "screw"]

# Turning half a turn: a part on its own axis stays put, a part orbiting at
# radius r moves 2r. 60 mm is far more than numerical noise and far less than
# the shaft height of any machine in the library.
MAX_DRIFT_M = 0.06

# Two kinds of part are meant to travel and are excluded.
#
# The library paints a reference stripe on every visible shaft (userData.tape)
# so you can see it turning — a stripe that stayed still would defeat its whole
# purpose. It sits one shaft radius off the axis and therefore moves exactly
# twice that on half a turn.
#
# Planet gears riding a carrier and a conrod on a crank orbit because that is
# the mechanism, not a mistake.
ORBITAL_NOTE = "shaft stripes, planet gears and crank throws travel by design"

TOOLBAR = [
    ("cond", "Show sample condition"),
    ("spin", "Rotate shafts"),
    ("xray", "See inside"),
    ("flowb", "Show flow"),
    ("sensb", "Sensors"),
    ("dirb", "Rotation"),
    ("arrb", "arrows"),
    ("guard", "Show guards"),
    ("reset", "Reset view"),
    ("more", "details"),
    ("png", "Save image"),
    ("glb", "Export 3D"),
]

PROBE = """
(args) => {
  const [models, maxDrift] = args;
  const out = {errors: [], models: {}};
  const lib = window.__lib;
  if (!lib) { out.errors.push('window.__lib missing'); return out; }
  out.counts = {equipment: lib.EQ.length, components: lib.CO.length};

  // A mesh travels by design if it, or anything above it, is a shaft stripe, a
  // planet gear on a carrier, or a crank throw. Checked by flag, so renaming a
  // part cannot quietly switch the check off.
  const travels = o => {
    for (let p = o; p; p = p.parent) {
      const u = p.userData || {};
      if (u.tape || u.orbital || u.crank) return true;
    }
    return false;
  };
  const spinAncestor = o => {
    for (let p = o; p; p = p.parent) if (p.userData && p.userData.spin) return p;
    return null;
  };
  const centre = o => new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3());

  for (const id of models) {
    const def = lib.EQ.find(d => d.id === id);
    if (!def) { out.errors.push('no such model: ' + id); continue; }
    lib.show(def);
    const obj = window.__obj();
    obj.updateMatrixWorld(true);

    // Every spinning group must have had its origin moved onto its own axis.
    let unpivoted = 0;
    obj.traverse(o => { if (o.userData.spin && !o.isMesh && !o.userData.pivoted) unpivoted++; });

    // Record each spinning mesh against its uuid, so before and after are
    // matched by identity rather than by traversal order.
    const before = new Map();
    obj.traverse(o => {
      if (!o.isMesh || !o.geometry) return;
      const spin = spinAncestor(o);
      if (!spin) return;
      const c = centre(o);
      before.set(o.uuid, {node: spin.name || '(unnamed)', travels: travels(o), c: [c.x, c.y, c.z]});
    });

    // Half a turn on every spinner, exactly as the animation loop drives it.
    obj.traverse(o => {
      if (!o.userData.spin) return;
      if (o.userData.spin === 'y') o.rotation.y += Math.PI; else o.rotation.x += Math.PI;
    });
    obj.updateMatrixWorld(true);

    let worst = 0, worstName = '', checked = 0, excused = 0;
    const drifted = [];
    obj.traverse(o => {
      const rec = before.get(o.uuid);
      if (!rec) return;
      if (rec.travels) { excused++; return; }
      checked++;
      const c = centre(o);
      const d = Math.hypot(c.x - rec.c[0], c.y - rec.c[1], c.z - rec.c[2]);
      if (d > worst) { worst = d; worstName = rec.node; }
      if (d > maxDrift) drifted.push({node: rec.node, drift: +d.toFixed(3)});
    });

    out.models[id] = {spinners: before.size, checked, excused, unpivoted,
                      worst: +worst.toFixed(4), worstName, drifted};
  }
  return out;
}
"""


HOST_PAGE = """<!doctype html><meta charset="utf-8"><title>bridge host</title>
<iframe id="f" src="./library.html" style="width:1200px;height:800px;border:0"></iframe>
<script>
window.__send = (msg) => document.getElementById('f').contentWindow.postMessage(
  Object.assign({target: 'senvia-3d'}, msg), window.location.origin);

window.__ask = (id) => new Promise(res => {
  const t = setTimeout(() => res({timeout: true}), 20000);
  window.addEventListener('message', function h(e) {
    if (e.data && e.data.source === 'senvia-3d' && e.data.type === 'shown') {
      clearTimeout(t); window.removeEventListener('message', h); res(e.data);
    }
  });
  const send = () => window.__send({type: 'show', id});
  // The frame may still be loading; ask again once it is up.
  send(); document.getElementById('f').addEventListener('load', send);
});
</script>"""


def check_bridge(page, port: int) -> dict:
    """Load the library inside a real same-origin frame and drive it."""
    host_url = f"http://127.0.0.1:{port}/__bridge_host.html"
    page.route(
        host_url,
        lambda route: route.fulfill(status=200, content_type="text/html", body=HOST_PAGE),
    )
    page.goto(host_url, wait_until="networkidle")
    return page.evaluate("() => window.__ask('mill')")


def serve(directory: Path, port: int = 0) -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    if not (WEB / "library.html").exists():
        raise SystemExit("no built library — run tools/build_web_library.py first")

    failures: list[str] = []
    httpd, port = serve(WEB)
    url = f"http://127.0.0.1:{port}/library.html"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on(
                "console",
                lambda m: page_errors.append("console.error: " + m.text)
                if m.type == "error"
                else None,
            )
            # Nothing may leave the machine: the viewer is vendored on purpose.
            external: list[str] = []
            page.on(
                "request",
                lambda r: external.append(r.url)
                if not r.url.startswith(("http://127.0.0.1", "data:", "blob:"))
                else None,
            )

            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => !!window.__lib", timeout=30000)

            # --- the toolbar the product asked for -------------------------
            for el_id, label in TOOLBAR:
                el = page.query_selector(f"#{el_id}")
                if el is None:
                    failures.append(f"toolbar: #{el_id} ({label}) missing")
                elif el.is_hidden():
                    failures.append(f"toolbar: #{el_id} ({label}) hidden")

            # --- the library is whole --------------------------------------
            result = page.evaluate(PROBE, [ROTATION_MODELS, MAX_DRIFT_M])
            counts = result.get("counts", {})
            if counts.get("equipment") != 48:
                failures.append(f"equipment models: {counts.get('equipment')} (expected 48)")
            if counts.get("components") != 46:
                failures.append(f"components: {counts.get('components')} (expected 46)")
            failures.extend(result.get("errors", []))

            # --- shafts turn in place --------------------------------------
            print(
                f"{'model':<10} {'spinning':>9} {'checked':>8} {'by design':>10} "
                f"{'unpivoted':>10} {'worst drift':>12}   node"
            )
            for model_id in ROTATION_MODELS:
                m = result["models"].get(model_id)
                if not m:
                    continue
                print(
                    f"{model_id:<10} {m['spinners']:>9} {m['checked']:>8} {m['excused']:>10} "
                    f"{m['unpivoted']:>10} {m['worst']:>12.4f}   {m['worstName'][:32]}"
                )
                if m["unpivoted"]:
                    failures.append(f"{model_id}: {m['unpivoted']} spinning groups never pivoted")
                if not m["checked"]:
                    failures.append(f"{model_id}: nothing was checked — the probe found no shafts")
                for d in m["drifted"]:
                    failures.append(
                        f"{model_id}: {d['node']} moved {d['drift']} m on half a turn — it "
                        f"swings around the machine instead of turning in place "
                        f"({ORBITAL_NOTE})"
                    )

            # --- the bridge answers ----------------------------------------
            # The bridge only posts to a real parent, so this needs a genuine
            # frame on the same origin, which is how it runs in the product.
            bridged = check_bridge(page, port)
            if bridged.get("timeout") or bridged.get("id") != "mill":
                failures.append(f"bridge: show did not report back ({bridged})")
            else:
                print(f"\nbridge: show('mill') -> {bridged['name']}, {bridged['points']} points")

            # Senvia has its own light/dark toggle, and a frame cannot see it.
            # Without this the library follows the operating system and a dark
            # app ends up framing a white panel.
            for wanted in ("dark", "light"):
                page.evaluate("(t) => window.__send({type: 'theme', theme: t})", wanted)
                page.wait_for_timeout(200)
                applied = page.frames[-1].evaluate(
                    "() => document.documentElement.getAttribute('data-theme')"
                )
                if applied != wanted:
                    failures.append(f"bridge: theme '{wanted}' not applied (got {applied!r})")
            print("bridge: theme follows the host in both directions")

            if page_errors:
                failures.extend(f"page error: {e}" for e in page_errors[:10])
            if external:
                failures.extend(f"external request: {u}" for u in sorted(set(external))[:5])

            browser.close()
    finally:
        httpd.shutdown()

    print(f"\nfailures: {len(failures)}")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

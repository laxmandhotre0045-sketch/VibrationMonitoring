"""
Run the Senvia 3D bug-hunt checks on every model (CI gate).
Exit code 1 if any Critical or Major finding is not on the by-design list.

    python tools/run_checks.py            # all models
    python tools/run_checks.py --report checks/last_report.json
"""
import argparse, json, pathlib, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from export_models import patched_library, ROOT

# Items confirmed as intended teaching views or real installations (see closing report)
BY_DESIGN = {
    ("B", "Rotating part not mounted on a shaft"): {"dgbb", "cyl", "sph", "taper", "angc", "thrust", "needle", "shaft", "girth"},
    ("D", "Floating part (touches nothing else)"): {"jaw", "sleeve", "crank"},
    ("D", "Parts below floor level"): {"vtp", "kiln", "hydro", "lift", "hoist"},
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--three"); ap.add_argument("--exporter")
    ap.add_argument("--report", default=str(ROOT / "checks" / "last_report.json"))
    a = ap.parse_args()
    js = (ROOT / "checks" / "bug_hunt.js").read_text(encoding="utf-8")
    page = patched_library(a.three, a.exporter)
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        pg = br.new_page(viewport={"width": 500, "height": 400})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(page.as_uri()); pg.wait_for_timeout(2000)
        pg.evaluate("window.__noMerge=true")
        res = pg.evaluate(js)
        br.close()
    fails, allowed = [], []
    for mid, r in res.items():
        if "err" in r:
            fails.append((mid, "BUILD", "Critical", r["err"])); continue
        for area, sev, what, detail in r["bugs"]:
            if area == "G":
                continue                      # budget measured on the merged scene by export_models.py
            if mid in BY_DESIGN.get((area, what), set()):
                allowed.append((mid, area, what)); continue
            if sev in ("Critical", "Major"):
                fails.append((mid, area, sev, f"{what}: {detail}"))
    pathlib.Path(a.report).write_text(json.dumps({"failures": fails, "by_design": allowed, "page_errors": errs}, indent=2))
    print(f"models checked: {len(res)} | failures: {len(fails)} | by design: {len(allowed)} | page errors: {len(errs)}")
    for f in fails[:40]:
        print("  FAIL", *f)
    sys.exit(1 if fails or errs else 0)

if __name__ == "__main__":
    main()

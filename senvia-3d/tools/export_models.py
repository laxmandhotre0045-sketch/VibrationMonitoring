"""
Export every model in the Senvia 3D library to GLB + JSON (Solution C asset store).

Usage:
    pip install -r requirements.txt && playwright install chromium
    python tools/export_models.py                      # all 94 models
    python tools/export_models.py --ids es mill gt     # selected library ids
    python tools/export_models.py --out assets/models --version 1.0.0

Output per model:  <out>/<MODEL_ID>/<version>/model.glb  and  model.json,  plus <out>/catalog.json
Offline use: --three path/to/three.min.js (r128) and --exporter path/to/GLTFExporter.js
"""
import argparse, base64, datetime, json, pathlib, re, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "legacy" / "senvia_3d_library.html"
THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
EXPORTER_CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/exporters/GLTFExporter.js"


def patched_library(three_path=None, exporter_path=None):
    """Copy of the library page with export hooks (local scripts, switch to skip mesh merging for metadata)."""
    s = LIB.read_text(encoding="utf-8")
    if three_path:
        s = s.replace(THREE_CDN, pathlib.Path(three_path).resolve().as_uri())
    if exporter_path:
        s = s.replace(EXPORTER_CDN, pathlib.Path(exporter_path).resolve().as_uri())
    s = re.sub(r"<link[^>]*fonts[^>]*>", "", s)
    s = s.replace("function mergeStatic(root){", "function mergeStatic(root){if(window.__noMerge)return;")
    if "window.__obj" not in s:
        s = s.replace("window.__lib={", "window.__obj=()=>obj;window.__lib={")
    tmp = pathlib.Path(tempfile.mkdtemp()) / "lib.html"
    tmp.write_text(s, encoding="utf-8")
    return tmp


# Metadata pass (unmerged scene): points, rotating parts, bearings
META_JS = r"""(id)=>{const L=window.__lib;const d=L.EQ.find(x=>x.id===id)||L.CO.find(x=>x.id===id);L.setMode(L.EQ.includes(d)?'eq':'co');
 window.__noMerge=true;L.show(d);const o=window.__obj();o.updateMatrixWorld(true);const V=THREE.Vector3,r=v=>+v.toFixed(3);
 const inInt=x=>{let p=x;while(p){if(p.userData&&p.userData.internal)return true;p=p.parent;}return false;};
 const pts=[],rot=[],brg=[];let n=0,k=0,fl=0;
 o.traverse(x=>{const u=x.userData||{};
  if(u.pt){n++;const w=x.getWorldPosition(new V());pts.push({id:'MP_'+String(n).padStart(2,'0'),label:u.pt.label,measure:u.pt.desc,position:[r(w.x),r(w.y),r(w.z)]});}
  if(u.spin&&!u.tape){const a=new V(u.spin==='y'?0:1,u.spin==='y'?1:0,0).transformDirection(x.parent.matrixWorld);const c=new THREE.Box3().setFromObject(x).getCenter(new V());
   rot.push({node:x.name||null,axis:[r(a.x),r(a.y),r(a.z)],centre:[r(c.x),r(c.y),r(c.z)],ratio:u.spinRate===undefined?1:u.spinRate,internal:inInt(x)});}
  if(u.flow)fl++;
  if(u.bearing){let ri=1e9,ro=0,hw=0,j=false;x.children.forEach(ch=>{if(ch.geometry&&ch.geometry.type==='LatheGeometry'){if(ch.material.name==='BABBITT')j=true;ch.geometry.parameters.points.forEach(p=>{ri=Math.min(ri,p.x);ro=Math.max(ro,p.x);hw=Math.max(hw,-p.y);});}});
   const w=x.getWorldPosition(new V());brg.push({id:'B'+(++k),type:j?'journal':'rolling',bore_mm:Math.round(2000*ri),od_mm:Math.round(2000*ro),width_mm:Math.round(2000*hw),position:[r(w.x),r(w.y),r(w.z)],designation:null});}});
 return {name:d.name,industry:d.ind||d.cat||'',drive:d.drive||'',kind:L.EQ.includes(d)?'equipment':'component',paint:d.paint||[],parts:d.parts||d.use||'',points:pts,rotating:rot,bearings:brg,flow_paths:fl};}"""

# GLB pass (merged, phone-ready scene); hidden layers are named so the app viewer can toggle them
GLB_JS = r"""async (id)=>{const L=window.__lib;const d=L.EQ.find(x=>x.id===id)||L.CO.find(x=>x.id===id);L.setMode(L.EQ.includes(d)?'eq':'co');
 window.__noMerge=false;L.show(d);const o=window.__obj();let i=0,f=0,s=0,dc=0,tri=0;
 o.traverse(x=>{const u=x.userData||{};if(u.internal&&!x.name)x.name='INTERNAL_'+(++i);if(u.flow&&!x.name)x.name='FLOW_'+(++f);if(u.sensor&&!x.name)x.name='SENSOR_'+(++s);
  if(x.isMesh){dc++;const g=x.geometry;tri+=(g.index?g.index.count:g.attributes.position.count)/3;}});
 const buf=await new Promise((ok,no)=>{try{new THREE.GLTFExporter().parse(o,ok,{binary:true,onlyVisible:false});}catch(e){no(e);}});
 let b='';const u8=new Uint8Array(buf);for(let q=0;q<u8.length;q+=0x8000)b+=String.fromCharCode.apply(null,u8.subarray(q,q+0x8000));
 return {glb:btoa(b),meshes:dc,triangles:Math.round(tri)};}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", help="library ids (e.g. es mill dgbb); default = all 94")
    ap.add_argument("--out", default=str(ROOT / "assets" / "models"))
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--three", default=None, help="local three.min.js (r128) for offline use")
    ap.add_argument("--exporter", default=None, help="local GLTFExporter.js (r128) for offline use")
    a = ap.parse_args()
    page_file = patched_library(a.three, a.exporter)
    out = pathlib.Path(a.out)
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        pg = br.new_page(viewport={"width": 800, "height": 600})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(page_file.as_uri())
        pg.wait_for_timeout(2000)
        if pg.evaluate("typeof THREE === 'undefined' || typeof THREE.GLTFExporter !== 'function'"):
            sys.exit("three.js or GLTFExporter did not load (check internet, or pass --three and --exporter)")
        ids = a.ids or pg.evaluate("(()=>{const L=window.__lib;return [...L.EQ,...L.CO].map(d=>d.id)})()")
        regmap = pg.evaluate(r"""(()=>{const s=document.documentElement.innerHTML;const m=s.slice(s.indexOf('const REG='),s.indexOf('};',s.indexOf('const REG=')));const r={};m.replace(/(\w+):'((?:EQ|CO)-[A-Z]{3}-\d{3})'/g,(a,k,v)=>{r[k]=v;return a;});return r;})()""")
        catalog = []
        for lid in ids:
            meta = pg.evaluate(META_JS, lid)
            g = pg.evaluate(GLB_JS, lid)
            mid = regmap.get(lid, lid)
            d = out / mid / a.version
            d.mkdir(parents=True, exist_ok=True)
            (d / "model.glb").write_bytes(base64.b64decode(g["glb"]))
            meta = {"model_id": mid, "library_id": lid, "version": a.version, "units": "m", "axes": "shaft along X, Y up",
                    "glb": f"{mid}/{a.version}/model.glb", **meta,
                    "stats": {"draw_calls": g["meshes"], "triangles": g["triangles"], "size_kb": round((d / "model.glb").stat().st_size / 1024)},
                    "exported": datetime.date.today().isoformat()}
            (d / "model.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            catalog.append({"model_id": mid, "name": meta["name"], "kind": meta["kind"], "version": a.version, "json": f"{mid}/{a.version}/model.json"})
            print(f"{mid:12s} {meta['name'][:38]:38s} {meta['stats']['size_kb']:6d} KB  {len(meta['points']):2d} points  {len(meta['bearings']):2d} bearings")
        (out / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        br.close()
    if errors:
        print("PAGE ERRORS:", errors)
        sys.exit(1)


if __name__ == "__main__":
    main()

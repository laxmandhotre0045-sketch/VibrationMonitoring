"""Build the Senvia-hosted copy of the 3D library from the kit source.

The library in ``legacy/senvia_3d_library.html`` is the source of truth: 48
machines, 46 components, correct rotation physics and the toolbar the product
team signed off on. Senvia serves its own copy rather than the kit file itself,
because three things have to change for it to run inside the product — and
nothing else does.

1. **three.js is vendored.** The kit loads r128 from two CDNs. Senvia loads the
   same revision from ``/senvia-3d/vendor/``, so the viewer works on a plant
   network with no internet and cannot break because a CDN moved. The revision
   is pinned deliberately: three changed its default colour management in r152,
   which would shift every RAL paint colour away from the library's own
   rendering. The app's own three (0.169) stays where it is; these two files are
   loaded as classic scripts inside the iframe and never meet it.

2. **Saving a file uses the browser.** The kit page ran as a Claude artifact,
   where writing a file goes through ``window.claude.use('downloads')``. Inside
   Senvia that capability does not exist, so "Save image" and "Export 3D (GLB)"
   would stay hidden — two of the features we are shipping. A plain object-URL
   download is the browser's own answer and needs no capability.

3. **A message bridge is appended.** The host page has to be able to say "show
   the end-suction pump" when somebody opens a pump, and to hear which
   measurement point was tapped. The bridge only reads ``window.__lib``, the
   hook the kit already publishes; it changes no library behaviour.

Every patch is asserted to apply exactly once. If a future kit revision moves
the text, this fails loudly here rather than silently shipping a page with a
dead toolbar or a CDN dependency nobody noticed.

Run: python tools/build_web_library.py
"""
from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
SOURCE = KIT / "legacy" / "senvia_3d_library.html"
OUTPUT = KIT.parent / "frontend" / "public" / "senvia-3d" / "library.html"

# --- 1. vendored three.js -------------------------------------------------

CDN_THREE = (
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
)
CDN_EXPORTER = (
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/exporters/'
    'GLTFExporter.js"></script>'
)
LOCAL_THREE = '<script src="./vendor/three.r128.min.js"></script>'
LOCAL_EXPORTER = '<script src="./vendor/GLTFExporter.r128.js"></script>'

# --- 1b. vendored typeface ------------------------------------------------

# Barlow is part of the library's look, and the kit pulls it from Google Fonts.
# On a plant network with no route out that request hangs and the page falls
# back to a system font, so the toolbar renders at a different width than the
# product was signed off at. The faces are vendored beside three.js.
CDN_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600'
    "&family=Barlow+Semi+Condensed:wght@600&display=swap\" rel=\"stylesheet\">"
)
LOCAL_FONTS = '<link href="./vendor/barlow.css" rel="stylesheet">'

# --- 2. saving a file without the Claude downloads capability -------------

CLAUDE_DOWNLOADS = (
    "(async()=>{try{if(window.claude&&window.claude.use)dl=await window.claude.use"
    "('downloads');}catch(e){dl=null;} document.getElementById('png').hidden=!dl; "
    "document.getElementById('glb').hidden=!dl||!THREE.GLTFExporter;})();"
)

BROWSER_DOWNLOADS = """\
/* Senvia: the kit page ran as a Claude artifact and saved files through that
   host's downloads capability. There is no such capability in the product, and
   without a `dl` both export buttons hide themselves on load. An object-URL
   download is what a browser offers instead, so both buttons work here as they
   do in the library. offer() and the two click handlers are untouched. */
dl={save:({filename,data})=>new Promise((res,rej)=>{try{
 const blob=(data instanceof Blob)?data:new Blob([data],{type:'application/octet-stream'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=filename;a.rel='noopener';document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),10000);res();
}catch(e){rej(e);}})};
document.getElementById('png').hidden=false;
document.getElementById('glb').hidden=!THREE.GLTFExporter;"""

# --- 3. the host bridge ---------------------------------------------------

# Appended after the library's own </script>, so window.__lib already exists.
# Everything here is additive: it drives the same show()/setMode() the toolbar
# drives, and reports back. Messages are confined to this origin — the iframe is
# served by Senvia itself, so there is never a cross-origin recipient, and no
# customer data travels either way. Only model ids do.
BRIDGE = """
<script>
/* Senvia host bridge — appended by tools/build_web_library.py, see that file. */
(function(){
 const lib=window.__lib;
 if(!lib){console.error('[senvia-3d] window.__lib missing; bridge disabled');return;}
 const ORIGIN=window.location.origin;
 // The library starts in Equipment mode (its last statement is setMode('eq')),
 // so the bridge starts believing the same. Tracking it here means selecting a
 // machine does not rebuild the first model of the list on the way past.
 let mode='eq';

 const find=id=>lib.EQ.find(d=>d.id===id)||lib.CO.find(d=>d.id===id)||null;

 function post(type,detail){
  try{ if(window.parent!==window) window.parent.postMessage(Object.assign({source:'senvia-3d',type:type},detail||{}),ORIGIN); }catch(e){}
 }

 function describe(def){
  return def?{id:def.id,name:def.name,drive:def.drive||'',industry:def.ind||def.cat||''}:null;
 }

 function showById(id){
  const def=find(id);
  if(!def){post('error',{message:'unknown model: '+id});return false;}
  const want=lib.EQ.indexOf(def)>=0?'eq':'co';
  if(want!==mode){lib.setMode(want);mode=want;}
  lib.show(def);
  post('shown',Object.assign({points:lib.get().points},describe(def)));
  return true;
 }

 window.addEventListener('message',function(e){
  if(e.origin!==ORIGIN)return;
  const m=e.data;
  if(!m||m.target!=='senvia-3d')return;
  if(m.type==='show'&&m.id)showById(m.id);
  // The library's stylesheet already answers to data-theme; left alone it
  // follows the operating system, which is how a dark Senvia ends up framing a
  // white panel.
  else if(m.type==='theme'&&(m.theme==='dark'||m.theme==='light'))document.documentElement.setAttribute('data-theme',m.theme);
  else if(m.type==='mode'&&(m.mode==='eq'||m.mode==='co')){lib.setMode(m.mode);mode=m.mode;post('mode',{mode:m.mode});}
  else if(m.type==='list')post('list',{
    equipment:lib.EQ.map(describe),
    components:lib.CO.map(describe)
  });
 });

 // A measurement point is the one thing the host genuinely needs to hear
 // about: tapping MP_03 is how a point gets bound to a sensor. The library
 // renders each point as a .pt button inside #markers, and rebuilds them on
 // every show(), so listen on the container rather than the buttons.
 const markers=document.getElementById('markers');
 if(markers)markers.addEventListener('click',function(e){
  const b=e.target.closest('.pt');
  if(!b)return;
  post('pointClick',{number:Number(b.textContent),label:b.getAttribute('aria-label')||''});
 });

 // ?model=<library id> preselects a machine, which is how opening a pump in
 // Senvia lands on the pump instead of whatever sorts first.
 const wanted=new URLSearchParams(window.location.search).get('model');
 if(wanted&&!showById(wanted))post('ready',{fallback:true});
 else post('ready',{model:wanted||null});
})();
</script>"""


def patch(html: str, old: str, new: str, what: str) -> str:
    """Replace `old` once, or fail saying which patch no longer applies."""
    found = html.count(old)
    if found != 1:
        raise SystemExit(
            f"build_web_library: expected exactly 1 occurrence of {what}, found {found}.\n"
            f"The kit library has changed. Re-read {SOURCE.name} and update this script."
        )
    return html.replace(old, new)


def build() -> int:
    html = SOURCE.read_text(encoding="utf8")

    html = patch(html, CDN_THREE, LOCAL_THREE, "the three.js CDN tag")
    html = patch(html, CDN_EXPORTER, LOCAL_EXPORTER, "the GLTFExporter CDN tag")
    html = patch(html, CDN_FONTS, LOCAL_FONTS, "the Google Fonts links")
    html = patch(html, CLAUDE_DOWNLOADS, BROWSER_DOWNLOADS, "the Claude downloads capability")

    # The bridge goes after the library's own closing script tag.
    tail = "</script>\n</body>"
    html = patch(html, tail, "</script>" + BRIDGE + "\n</body>", "the closing script tag")

    # Nothing may still reach for a CDN: the point of vendoring is a viewer that
    # works on a plant network with no route to the internet.
    for host in ("cdnjs.cloudflare.com", "cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"):
        if host in html:
            raise SystemExit(f"build_web_library: {host} still referenced after patching")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf8")

    src_kb = len(SOURCE.read_bytes()) // 1024
    out_kb = len(OUTPUT.read_bytes()) // 1024
    print(f"built {OUTPUT}  ({src_kb} KB source -> {out_kb} KB)")
    print("patches applied: vendored three, vendored Barlow, browser downloads, host bridge")
    return 0


if __name__ == "__main__":
    sys.exit(build())

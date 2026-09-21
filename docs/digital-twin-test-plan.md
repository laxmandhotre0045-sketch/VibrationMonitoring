# Digital Twin v2 — test plan

Covers the rebuilt 3D viewer behind the `digitalTwinV2` flag.

## Running the automated tests

```bash
cd frontend
npm test          # vitest, 43 tests
npm run build     # tsc + vite production build
```

The flag defaults **on in development, off in production builds**. To force it
either way in a browser:

```js
__ff.set("digitalTwinV2", true)   // or false, or null to reset
location.reload()
```

---

## 1. Automated coverage (43 tests)

### `label-layout.test.ts` — 31 tests
The no-overlap guarantee is the one rule worth proving rather than eyeballing,
so the spreading function is pure and tested directly.

- No overlap with 6 sensor chips and 4 bearing chips at **400, 640, 1024 and
  1920 px** stage widths — each swept through **72 camera angles** (anchors
  moving right across and beyond the stage).
- Chips that already clear each other are left centred on their anchors.
- Rows clamp inside the stage at both edges.
- A row too wide to fit still never overlaps (containment yields, separation
  does not).
- Visual order follows anchor x; DOM order follows input order.
- Ties break on id, so chips cannot swap sides between frames.
- Chip movement is continuous as an anchor moves — no jumps.
- Custom gap and padding honoured; anchors preserved for leader lines.

### `xray.test.ts` — 12 tests
Everything behind *"x-ray on and off leaves no material stuck transparent"*.

- Originals are cloned, never mutated; two meshes sharing one material get
  separate clones.
- Fades to 14 % with `depthWrite` off and shadow casting suppressed.
- An **opaque** material restores to exactly opaque; an **already-transparent**
  one restores to its own opacity and flags, not to opaque.
- No drift over 12 on/off cycles; a toggle interrupted mid-fade still restores.
- Multi-material meshes handled per slot.
- `dispose()` puts the original materials back **even mid-fade** — this is what
  protects a machine-type switch.
- Empty x-ray layer does not throw.

---

## 2. Manual test script

Open Equipment Master → new equipment, with `digitalTwinV2` on.

### 2.1 Model loading
1. Step 1, leave Machine Type blank → generic machine, with the note explaining
   it is generic.
2. Pick **Fan** → detailed motor-driven overhung fan appears, on the floor,
   lit, with a soft shadow.
3. Cycle through Motor, Pump, Blower, Compressor, Gearbox, Turbine, Generator,
   DG Set, Conveyor, Crusher, Mixer, Agitator. Every one renders; the last four
   show the generic model plus its note.
4. Drop a `fan.glb` into `frontend/public/models/` → it replaces the procedural
   fan with no code change.

### 2.2 Interaction
5. Drag to rotate, scroll to zoom, right-drag to pan. Camera cannot go below
   the floor.
6. **Front**, **Side**, **Top**, **Reset view** — each eases over ~650 ms and
   frames the whole machine.
7. Resize the window from ~400 px to full width; the model stays framed.

### 2.3 Labels
8. Six sensor chips along the top, bearing chips along the bottom, each with a
   leader line to its anchor dot.
9. Orbit continuously — **no two chips ever overlap**.
10. Narrow the window below 640 px — chips collapse to the id only.
11. Rotate so an anchor goes behind the machine → its leader turns **dashed**.
    Switch on x-ray → it goes solid again.
12. **Labels** toggle hides and restores all chips and leaders.

### 2.4 Two-way highlighting
13. Hover a side-panel row → the matching chip and 3D marker highlight within a
    frame.
14. Hover a 3D marker → chip and row highlight.
15. Hover a chip → row and marker highlight.
16. Click any of the three → camera flies to that anchor and the selection pins.
17. **Tab** through rows and chips → visible focus ring; focus highlights the
    same trio; **Enter**/**Space** selects.
18. Drag across the canvas over a marker → does **not** select (drag ≠ click).

### 2.5 X-ray and rotor
19. **X-ray casing** on → shells fade, shaft and bearings visible, configured
    bearings glow amber.
20. Off → everything solid again, nothing left translucent.
21. Toggle x-ray on, then switch machine type, then off → no stuck materials.
22. **Run shaft** → rotor spins about the shaft axis, no wobble. Off → stops.
23. System setting *reduce motion* on → **Run shaft** is disabled with a tooltip
    saying why.

### 2.6 Configuration binding
24. Step 3, type a DE bearing number → the DE bearing turns amber and its chip
    shows the number. Clear it → back to "Not configured".
25. All four bearing positions are listed; the two the form does not capture
    stay unconfigured outlines.
26. Step 5, change a mounting row's **Orientation** → the marker moves to the
    matching face (vertical on top, horizontal on the side, axial on the end).
27. Change a row's **Mounting Location** → the marker moves to that part.
28. Pick a location the model has no part for (e.g. Gearbox Input on a pump) →
    marker sits on the foundation, chip muted, side panel says so.
29. Add a sensor under Additional Sensors → it appears as the next channel.
    Remove it → its marker and chip disappear.

### 2.7 Robustness
30. Step 6 → full twin plus the summary list.
31. **Save & Finish** → saves exactly as before; no new fields in the payload.
32. Reload with the flag **off** → the original viewer renders, unchanged.
33. Scroll the panel off-screen → rendering stops (check the Performance panel).
    Scroll back → resumes.
34. Switch to another tab and back → same.
35. Disable WebGL (`chrome://flags` → *Disable WebGL*) → readable "3D view
    unavailable" message, side panel still usable, form still saves.
36. Mount/unmount 20 times (navigate in and out of Equipment Master) →
    `renderer.info.memory` does not grow and the 21st render still works.

### 2.8 Browsers and themes
37. Repeat 2.1–2.5 in current **Chrome**, **Edge** and **Firefox**.
38. Repeat in light and dark theme.

---

## 3. Known gaps

- **`digital-twin-3d.html` was never supplied**, so the procedural fan was
  rebuilt from the screenshots rather than ported. It matches the reference
  layout (finned motor → coupling → two pedestals → overhung impeller in a
  scroll housing) but is not line-for-line the original.
- **No GLB files exist yet.** Every machine type currently renders its
  procedural stand-in. The GLB path is implemented and scanned for, but has not
  been exercised against a real asset.
- **No preview PNGs yet** — the loading placeholder falls back to the spinner
  alone until `public/models/previews/{type}.png` exist.
- **`status` (ok/alert/danger) is plumbed but never set.** The setup flow has no
  condition data; populate `status` in `adapt-equipment.ts` and the marker and
  chip colour follow.
- **Dark theme is honoured by the viewer but inert app-wide**: `ThemeProvider`
  sets `.dark` on `<html>` and Tailwind is configured for it, but `index.css`
  defines no dark token values, so the rest of the page stays light.
- **Gearbox output shaft does not spin** — only one `ROTOR` group is animated.
  Real GLBs carry a proper `ROTOR` and are unaffected.

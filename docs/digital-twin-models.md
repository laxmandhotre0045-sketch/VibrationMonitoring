# Digital Twin — 3D model specification

This document is for the 3D artist producing the GLB models the SensoVibe
Digital Twin loads. Everything here is a contract the code depends on: the
viewer finds parts **by node name**, never by hard-coded coordinates, so you can
move, rescale or re-model anything as long as the names and the conventions
below are kept.

If a model is missing, the viewer falls back to a built-in procedural machine of
the same type. Nothing breaks while you work — a half-finished model simply is
not shipped yet.

---

## 1. Deliverables

| Machine type | File | Budget |
|---|---|---|
| Fan | `public/models/fan.glb` | ≤ 2 MB |
| Pump | `public/models/pump.glb` | ≤ 2 MB |
| Blower | `public/models/blower.glb` | ≤ 2 MB |
| Motor | `public/models/motor.glb` | ≤ 2 MB |
| Gearbox | `public/models/gearbox.glb` | ≤ 2 MB |

Optionally, a still of each model for the loading placeholder:
`public/models/previews/{type}.png`, roughly 800 × 500, transparent background.

**Format:** glTF 2.0 binary (`.glb`), **Meshopt-compressed**. In Blender:
*File → Export → glTF 2.0*, Format `glTF Binary`, and under *Compression* choose
Meshopt (or run `gltfpack -i in.glb -o out.glb -cc` afterwards). Draco is **not**
supported — the viewer wires up the Meshopt decoder only.

---

## 2. Orientation, scale and origin

These three are the difference between a model that drops in and one that needs
code changes.

```
        +Y  up
         │
         │
         └───── +X   along the shaft, pointing from the
        ╱             non-drive end toward the drive end
      +Z
      across the shaft (horizontal, at 90° to it)
```

- **Shaft on +X.** The rotating axis runs along world X. The drive end is the
  +X end. This is what lets the viewer turn a sensor's *Axial* orientation into
  a direction without being told which way the machine faces.
- **1 unit = 100 mm.** A 2 m long pump set is 20 units. The viewer will warn and
  auto-rescale anything whose longest dimension is under 1 or over 60 units, but
  please get this right — auto-rescaling makes the sensor markers the wrong size
  relative to the machine.
- **Origin at the shaft centre line, on the floor plane.** Put the model's
  origin where the shaft axis meets the base. Y = 0 is the ground; the viewer
  drops a shadow there.
- **Apply all transforms before export** (in Blender: *Object → Apply → All
  Transforms*). Unapplied scale on an anchor empty rotates the sensor marker
  incorrectly.

---

## 3. Node naming

### 3.1 Sensor mounting points — `CH…` empties

Place an **Empty** at every point an analyst would stud-mount an accelerometer:
each bearing housing, the casing, the foundation.

> **The empty's local +Y must point along the measurement axis.**

That is the whole trick: the accelerometer model is built pointing up its own
+Y, so parenting it to your empty aims it correctly with no code involved. A
*Vertical* mounting point has +Y up; a *Horizontal* one has +Y pointing out
sideways (along world Z); an *Axial* one has +Y pointing along the shaft
(world X, away from the machine).

Name them in **either** of these ways:

**Preferred — semantic names.** Self-describing and impossible to mis-map:

```
CH_MOTOR_DE_H      CH_MOTOR_DE_V      CH_MOTOR_DE_A
CH_MOTOR_NDE_H     CH_MOTOR_NDE_V     CH_MOTOR_NDE_A
CH_FAN_DE_H        CH_FAN_DE_V        CH_FAN_DE_A
CH_FAN_NDE_H       CH_FAN_NDE_V       CH_FAN_NDE_A
CH_FAN_HOUSING_H   CH_FOUNDATION_V    …
```

Format: `CH_<LOCATION>_<AXIS>` where `<AXIS>` is one of
`H` horizontal · `V` vertical · `A` axial · `R` radial · `T` tangential.

**Also accepted — numbered names with custom properties.** Name the empties
`CH1`, `CH2`, … and add two glTF **custom properties** to each (in Blender:
*Object Properties → Custom Properties*):

| Property | Example |
|---|---|
| `location` | `Fan DE` |
| `axis` | `Horizontal` |

Numbered names without those properties will still load, but the viewer can only
match them if a sensor's anchor happens to be that literal name — so always add
the properties if you use `CH1…CHn`.

### 3.2 Locations to provide

Use the location names below, because they are what the Equipment Master form
records. The right-hand column is the slug to use in a semantic node name.

| Form mounting location | Slug |
|---|---|
| Bearing Housing DE | depends on machine — `FAN_DE`, `PUMP_DE`, `MOTOR_DE`, `GEARBOX_INPUT` |
| Bearing Housing NDE | `FAN_NDE`, `PUMP_NDE`, `MOTOR_NDE`, `GEARBOX_OUTPUT` |
| Motor DE | `MOTOR_DE` |
| Motor NDE | `MOTOR_NDE` |
| Gearbox Input | `GEARBOX_INPUT` |
| Gearbox Output | `GEARBOX_OUTPUT` |
| Pump Casing | `PUMP_CASING` |
| Fan Housing | `FAN_HOUSING` |
| Compressor Housing | `COMPRESSOR_CASING` |
| Foundation | `FOUNDATION` |

Provide **H, V and A** for every bearing housing at minimum. R and T are
optional; if absent the viewer falls back gracefully.

### 3.3 Bearing centres — `BRG_…` empties

Place an Empty at the **centre of each bearing**, on the shaft axis:

```
BRG_MOTOR_DE    BRG_MOTOR_NDE    BRG_FAN_DE    BRG_FAN_NDE
BRG_PUMP_DE     BRG_PUMP_NDE     BRG_GEARBOX_INPUT    BRG_GEARBOX_OUTPUT
```

The viewer draws its own bearing ring at each of these — amber when the operator
has configured that bearing, a faint outline when they have not. You do not need
to model the bearing itself, but if you do, keep it inside the housing where the
x-ray mode will reveal it.

Include **every** bearing the machine has, not just two. A fan train has four
(motor DE/NDE and fan DE/NDE) and all four are shown.

### 3.4 The x-ray layer

Any mesh whose name contains **`casing`**, **`housing`**, **`cover`** or
**`guard`** (case-insensitive) fades to 14 % opacity when the operator switches
on *X-ray casing*.

Name outer shells accordingly — `motor_casing`, `fan_housing`, `terminal_cover`,
`coupling_guard`. Keep shafts, rotors, impellers, bearings, feet and plinths out
of that list so the machine keeps its shape when the shells go.

### 3.5 The rotating assembly — `ROTOR`

Put everything that spins under a single Empty or group named exactly **`ROTOR`**:
shaft, rotor core, coupling halves, impeller hub and blades.

> **`ROTOR`'s origin must sit on the shaft axis, and its local X must run along
> that axis.**

The viewer spins this group about its local X for the *Run shaft* toggle. If the
origin is off-axis the assembly will orbit instead of rotating.

A gearbox has two shafts on different centres. Put the input assembly under
`ROTOR` and leave the output static, or nest a second empty named `ROTOR_2` —
only `ROTOR` is currently animated.

---

## 4. Materials

- Use **PBR metal/rough** materials (Principled BSDF). The viewer lights the
  scene with a PMREM environment plus a key, rim and fill, under ACES filmic
  tone mapping at 0.78 exposure, and sets `envMapIntensity` to 0.6 on import.
- **Keep material count low** — under ~10 per model. Materials are cloned per
  mesh for x-ray, so a model with 200 unique materials costs 200 clones.
- Bake nothing that depends on lighting. No baked shadows or AO into base
  colour; the viewer casts real shadows.
- Textures are optional and count against the 2 MB budget. Flat PBR colours look
  correct under this lighting and are usually the better trade.

---

## 5. Level of detail

The viewer shows the machine at roughly 300–450 px tall. Aim for:

- **20k–60k triangles** per model.
- Chamfers and fillets where they catch the key light; no sub-millimetre detail.
- Bolts, fins and blades as simple geometry — they read at this size, individual
  threads do not.
- No interior detail except what x-ray should reveal: shaft, rotor, bearings.

---

## 6. Checklist before handing over

- [ ] Exported as `.glb`, Meshopt-compressed, under 2 MB
- [ ] Shaft runs along **+X**, drive end at +X
- [ ] 1 unit = 100 mm
- [ ] Origin on the shaft axis at floor level; all transforms applied
- [ ] A `CH…` empty at every mounting point, **local +Y along the measurement axis**
- [ ] H, V and A provided for each bearing housing
- [ ] A `BRG_…` empty at every bearing centre, on the shaft axis
- [ ] Outer shells named with `casing` / `housing` / `cover` / `guard`
- [ ] Everything that spins under `ROTOR`, origin on the axis, local X along it
- [ ] PBR materials, under ~10 of them, no baked lighting
- [ ] 20k–60k triangles

---

## 7. Checking your work

Drop the file into `frontend/public/models/`, open Equipment Master, and pick
that machine type in Step 1. The viewer loads the GLB in place of the procedural
stand-in automatically — no code change and no restart beyond the dev server's
own reload.

Then confirm:

1. The machine sits on the floor, right way up, at a sensible size.
2. Sensor markers appear at your `CH…` empties, each pointing the right way —
   vertical ones standing up, horizontal ones out the side, axial ones off the
   end face.
3. Bearing rings appear at your `BRG_…` empties.
4. *X-ray casing* fades the shells and reveals the shaft and bearings.
5. *Run shaft* spins the rotor about its own axis without wobbling.

The browser console warns if the model is scaled far from the expected range.

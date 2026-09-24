# Digital twin: machine model conventions

Every model in `frontend/public/models/` follows these rules. The viewer reads
node **names** and node **transforms** — it never hardcodes coordinates per
machine type, so a model can be re-modelled, rescaled or replaced freely as long
as the names below are kept.

If a model is missing or fails to parse, the viewer falls back to a procedural
machine of the same family. Nothing breaks while a model is being worked on.

## Axes and units

* Metres. Y up. **X is the shaft axis**, drive end toward +X. Z is the horizontal cross-axis.
* Origin sits at floor level, centred on the machine.
* Authored at real physical size, so the viewer's auto-fit works with no per-type tuning.

## Node names

| Pattern | Meaning |
|---|---|
| `SNS_<LOCATION>_<H\|V\|A>` | Sensor mounting point. **Local +Y points along the measurement axis.** |
| `BRG_<LOCATION>` | Bearing anchor, at the bearing centre. |
| `CASING_*` | Meshes that fade in x-ray mode (housings, covers, guards, volutes). |
| `ROTOR` | Parent node for everything that rotates. Spinning it rotates about local X. |

`<LOCATION>` uses underscores: `MOTOR_DE`, `FAN_NDE`, `GB_HSS_DE`, `MAIN_BRG`.
Axis letters are H horizontal (+Z), V vertical (+Y), A axial (±X).

**Do not name sensor nodes CH1…CH6.** Channel numbers are positional and shift
when a sensor is deleted. The frontend adapter builds the node name from
`mounting_location` + `orientation`; the CH number is only the chip's label.

Place anchors on the **node transform**, not baked into mesh vertices. A node
whose transform is identity hands the viewer the origin, not the anchor.

## Adapter mapping

```
mounting_location  "Bearing Housing DE"  ->  FAN_DE   (on a fan)
orientation        "Horizontal"          ->  H
node name          SNS_FAN_DE_H
```

The location half lives in `LOCATION_ALIAS` in
`frontend/src/lib/digital-twin/machine-type-map.ts`, keyed by machine family.
Adding a machine type is a data edit in that file — three tables, no new code.
`frontend/src/lib/digital-twin/__tests__/glb-contract.test.ts` checks every
machine type × every mounting location × every orientation against the real
files, so a rename that breaks the mapping fails the suite rather than silently
dropping a marker.

## Every mounting location needs an anchor

Step 5 offers these: Bearing Housing DE/NDE, Motor DE/NDE, Gearbox Input/Output,
Pump Casing, Fan Housing, Compressor Housing, Foundation. **Every one must
resolve to a node on every model**, or a sensor mounted there has nowhere to
land and its marker silently disappears.

Two of those are not bearings and are easy to forget:

* `SNS_FOUNDATION_*` — on the baseplate, at the machine's centre. A static
  mounting point: there is no rotating axis under it, so H/V/A follow the world
  axes. Every model has one.
* A casing point — `PUMP_CASING`, `FAN_HOUSING`, `COMP_HOUSING`, … — on the
  housing rather than a bearing.

**Vertical machines.** A top-entry mixer or agitator runs its shaft down, not
along X. Those models orient the `ROTOR` node so its local X points up, which is
what makes the shaft turn about itself instead of swinging around the model, and
their H/V/A anchors are placed by hand: V runs along the shaft, H and A across
it — the opposite of a horizontal machine.

## Current library

| File | Sensor anchors | Bearing anchors | Locations |
|---|---|---|---|
| `motor.glb` | 12 | 2 | MOTOR_DE/NDE, MOTOR_HOUSING, FOUNDATION |
| `pump.glb` | 18 | 4 | MOTOR_*, PUMP_*, PUMP_CASING, FOUNDATION |
| `fan.glb` | 18 | 4 | MOTOR_*, FAN_*, FAN_HOUSING, FOUNDATION |
| `blower.glb` | 18 | 4 | MOTOR_*, BLOWER_*, BLOWER_HOUSING, FOUNDATION (belt driven) |
| `compressor.glb` | 18 | 4 | MOTOR_*, COMP_*, COMP_HOUSING, FOUNDATION (twin screw) |
| `gearbox.glb` | 18 | 4 | GB_HSS_*, GB_LSS_*, GB_HOUSING, FOUNDATION |
| `spindle.glb` | 12 | 3 | SPINDLE_FRONT, SPINDLE_FRONT2, SPINDLE_REAR, SPINDLE_HOUSING, FOUNDATION |
| `turbine.glb` | 18 | 4 | TURB_*, GEN_*, TURB_CASING, FOUNDATION |
| `wind-turbine-drivetrain.glb` | 21 | 5 | MAIN_BRG, GB_HSS_*, GEN_*, GB_HOUSING, FOUNDATION |
| `dg-set.glb` | 15 | 3 | ENGINE_DE, ALT_*, ENGINE_BLOCK, FOUNDATION |
| `generator.glb` | 12 | 2 | GEN_DE/NDE, GEN_HOUSING, FOUNDATION |
| `conveyor.glb` | 15 | 3 | PULLEY_DE/NDE, TAIL_BRG, CONV_FRAME, FOUNDATION |
| `crusher.glb` | 18 | 4 | CRSH_DE/NDE, DRIVE_*, CRSH_HOUSING, FOUNDATION |
| `mixer.glb` | 12 | 2 | MIX_DE/NDE, MIX_HOUSING, FOUNDATION (vertical shaft) |
| `agitator.glb` | 12 | 2 | MIX_DE/NDE, MIX_HOUSING, FOUNDATION (vertical shaft) |
| `machine-train.glb` | 24 | 6 | MOTOR_*, GB_IN_*, DRIVEN_*, DRIVEN_HOUSING, FOUNDATION |

47–188 kB uncompressed, 1.7 MB for the set. Run them through `gltf-transform` with Meshopt before
shipping; `MeshoptDecoder` is already wired into the `GLTFLoader`.

## Which machine type gets which model

Every Step 1 machine type now has a model of its own:

| Machine Type | Model |
|---|---|
| Motor | `motor.glb` |
| Generator | `generator.glb` |
| Pump | `pump.glb` |
| Fan | `fan.glb` |
| Blower | `blower.glb` |
| Compressor | `compressor.glb` |
| Gearbox | `gearbox.glb` |
| Turbine | `turbine.glb` |
| DG Set | `dg-set.glb` |
| Spindle | `spindle.glb` |
| Wind Turbine | `wind-turbine-drivetrain.glb` |
| Conveyor | `conveyor.glb` |
| Crusher | `crusher.glb` |
| Mixer | `mixer.glb` |
| Agitator | `agitator.glb` |

`machine-train.glb` — a motor, gearbox and driven shaft on one base — is no
longer referenced now that each of those types has a model of its own. It is
kept because it is the right stand-in for the next driven-equipment type added.

## Regenerating or replacing a model

The current files are parametric stand-ins generated by
`frontend/scripts/build_models.py` (Python + trimesh + shapely + mapbox_earcut).
They are correct in proportion, layout and naming, but they are not any
manufacturer's specific machine.

```
python frontend/scripts/build_models.py
```

When a real scanned or CAD-derived model arrives:

1. Confirm the axes and units above.
2. Rename its nodes to match the table.
3. Move anchors onto node transforms with +Y along the measurement axis.
4. Include `SNS_FOUNDATION_*` and the casing point for that type.
5. Drop it in `frontend/public/models/<type>.glb`.

No viewer code changes. Run the frontend suite — `glb-contract.test.ts` will
tell you immediately if a name is missing.

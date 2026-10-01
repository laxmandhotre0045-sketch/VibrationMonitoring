/**
 * Which machine in the Senvia 3D library stands for each `machine_type`.
 *
 * The library (`public/senvia-3d/library.html`, built from the senvia-3d kit by
 * `tools/build_web_library.py`) draws 48 machines and 46 components. Senvia's
 * equipment master offers a shorter list of machine types, so opening a pump
 * has to land on a pump rather than on whatever the library happens to show
 * first.
 *
 * The ids here are the library's own short ids — the `id` on each entry of
 * `window.__lib.EQ` — not the catalogue's `EQ-xxx-nnn` model ids. Both are
 * listed below because the model id is what the exported GLB and the asset
 * store are keyed by, and somebody reading this will want to find the file.
 *
 * Nothing falls back silently. A machine type with no sensible match resolves
 * to `null` and the viewer opens on the library's own first entry with every
 * machine still reachable from the chips, which is honest about the fact that
 * we are not claiming to draw that exact asset.
 */

/** One machine in the library. */
export interface LibraryModel {
  /** The library's short id — what `show()` and `?model=` take. */
  id: string;
  /** Catalogue id, the key the exported GLB and model.json are stored under. */
  modelId: string;
  name: string;
  industry: string;
}

/**
 * Every machine the library draws, in the order its chips list them.
 *
 * Kept here so a mapping can be checked against reality at build time rather
 * than at the moment a plant engineer opens a machine and gets a blank stage.
 * `library-models.test.ts` reads the shipped `library.html` and fails if this
 * list and that file ever disagree.
 */
export const LIBRARY_EQUIPMENT: readonly LibraryModel[] = Object.freeze([
  { id: "es", modelId: "EQ-UTL-001", name: "End-suction pump", industry: "Utilities & process" },
  { id: "ms", modelId: "EQ-UTL-002", name: "Multistage pump", industry: "Utilities & process" },
  { id: "mono", modelId: "EQ-UTL-003", name: "Close-coupled monoblock pump", industry: "Utilities & process" },
  { id: "vtp", modelId: "EQ-UTL-004", name: "Vertical turbine pump", industry: "Utilities & process" },
  { id: "split", modelId: "EQ-UTL-005", name: "Split-case pump", industry: "Utilities & process" },
  { id: "inline", modelId: "EQ-UTL-006", name: "Inline pump", industry: "Utilities & process" },
  { id: "fan", modelId: "EQ-UTL-007", name: "Centrifugal fan", industry: "Utilities & process" },
  { id: "beltfan", modelId: "EQ-UTL-008", name: "Centrifugal fan (belt)", industry: "Utilities & process" },
  { id: "axfan", modelId: "EQ-UTL-009", name: "Axial fan (duct)", industry: "Utilities & process" },
  { id: "roots", modelId: "EQ-UTL-010", name: "Roots blower", industry: "Utilities & process" },
  { id: "screw", modelId: "EQ-UTL-011", name: "Screw compressor", industry: "Utilities & process" },
  { id: "recip", modelId: "EQ-UTL-012", name: "Reciprocating compressor", industry: "Utilities & process" },
  { id: "turbo", modelId: "EQ-UTL-013", name: "Integrally geared centrifugal compressor", industry: "Utilities & process" },
  { id: "ct", modelId: "EQ-UTL-014", name: "Cooling tower fan", industry: "Utilities & process" },
  { id: "chiller", modelId: "EQ-UTL-015", name: "Screw chiller", industry: "Utilities & process" },
  { id: "ahu", modelId: "EQ-UTL-016", name: "Air handling unit fan", industry: "Utilities & process" },
  { id: "mg", modelId: "EQ-PWR-001", name: "Motor-generator test bench", industry: "Power & energy" },
  { id: "dg", modelId: "EQ-PWR-002", name: "Diesel generator set", industry: "Power & energy" },
  { id: "stg", modelId: "EQ-PWR-003", name: "Steam turbine generator", industry: "Power & energy" },
  { id: "wtg", modelId: "EQ-PWR-004", name: "Wind turbine drivetrain", industry: "Power & energy" },
  { id: "bfp", modelId: "EQ-PWR-005", name: "Boiler feed pump", industry: "Power & energy" },
  { id: "idfan", modelId: "EQ-PWR-006", name: "Induced draft (ID) fan", industry: "Power & energy" },
  { id: "coalmill", modelId: "EQ-PWR-007", name: "Coal mill (bowl / vertical roller)", industry: "Power & energy" },
  { id: "hydro", modelId: "EQ-PWR-008", name: "Hydro turbine generator (vertical)", industry: "Power & energy" },
  { id: "gt", modelId: "EQ-PWR-009", name: "Gas turbine generator package", industry: "Power & energy" },
  { id: "conv", modelId: "EQ-CMS-001", name: "Belt conveyor drive", industry: "Cement, mining & steel" },
  { id: "mill", modelId: "EQ-CMS-002", name: "Ball mill", industry: "Cement, mining & steel" },
  { id: "crusher", modelId: "EQ-CMS-003", name: "Cone crusher", industry: "Cement, mining & steel" },
  { id: "gb", modelId: "EQ-CMS-004", name: "Gearbox drive", industry: "Cement, mining & steel" },
  { id: "jawcr", modelId: "EQ-CMS-005", name: "Jaw crusher", industry: "Cement, mining & steel" },
  { id: "vrm", modelId: "EQ-CMS-006", name: "Vertical roller mill (VRM)", industry: "Cement, mining & steel" },
  { id: "kiln", modelId: "EQ-CMS-007", name: "Rotary kiln drive and support", industry: "Cement, mining & steel" },
  { id: "screen", modelId: "EQ-CMS-008", name: "Vibrating screen", industry: "Cement, mining & steel" },
  { id: "belev", modelId: "EQ-CMS-009", name: "Bucket elevator", industry: "Cement, mining & steel" },
  { id: "rmill", modelId: "EQ-CMS-010", name: "Rolling mill stand", industry: "Cement, mining & steel" },
  { id: "hoist", modelId: "EQ-CMS-011", name: "EOT crane hoist", industry: "Cement, mining & steel" },
  { id: "agit", modelId: "EQ-CHM-001", name: "Agitator / mixer", industry: "Chemical & pharma" },
  { id: "api", modelId: "EQ-CHM-002", name: "API process pump (OH2)", industry: "Chemical & pharma" },
  { id: "decanter", modelId: "EQ-CHM-003", name: "Decanter centrifuge", industry: "Chemical & pharma" },
  { id: "extruder", modelId: "EQ-CHM-004", name: "Plastic extruder", industry: "Chemical & pharma" },
  { id: "tablet", modelId: "EQ-CHM-005", name: "Rotary tablet press", industry: "Chemical & pharma" },
  { id: "recip618", modelId: "EQ-CHM-006", name: "Reciprocating process compressor (API 618)", industry: "Chemical & pharma" },
  { id: "paper", modelId: "EQ-OTH-001", name: "Paper machine dryer roll", industry: "Paper, marine, water & other" },
  { id: "marine", modelId: "EQ-OTH-002", name: "Marine propulsion shaft line", industry: "Paper, marine, water & other" },
  { id: "sub", modelId: "EQ-OTH-003", name: "Submersible sewage pump", industry: "Paper, marine, water & other" },
  { id: "aerator", modelId: "EQ-OTH-004", name: "Surface aerator", industry: "Paper, marine, water & other" },
  { id: "cnc", modelId: "EQ-OTH-005", name: "CNC machining centre spindle", industry: "Paper, marine, water & other" },
  { id: "lift", modelId: "EQ-OTH-006", name: "Elevator traction machine", industry: "Paper, marine, water & other" },
]);

/**
 * `machine_type` → library id, keyed lower-case because the lookup values are
 * title-cased ("DG Set") while older rows are not.
 *
 * Where a type has no exact twin in the library the nearest real machine is
 * used and the reason is written down, because "why is my motor drawn on a test
 * bench" is a question somebody will ask:
 *
 * - **Motor** and **Generator** both open the motor-generator bench, which is
 *   the only model carrying either as a machine in its own right rather than as
 *   the driver of something else.
 * - **Turbine** opens the steam turbine generator; the gas turbine package is
 *   reachable from the chips for anyone who wants it.
 * - **Mixer** and **Agitator** are one model in the library, which is how the
 *   industry treats them.
 * - **Blower** opens the Roots blower rather than a centrifugal fan: a blower
 *   is a positive-displacement machine and its vibration signature follows the
 *   lobes, not the blades.
 */
const LIBRARY_ID_BY_MACHINE_TYPE: Readonly<Record<string, string>> = Object.freeze({
  motor: "mg",
  pump: "es",
  fan: "fan",
  blower: "roots",
  compressor: "screw",
  gearbox: "gb",
  turbine: "stg",
  generator: "mg",
  "dg set": "dg",
  conveyor: "conv",
  crusher: "crusher",
  mixer: "agit",
  agitator: "agit",
  "wind turbine": "wtg",
  spindle: "cnc",
});

/** Every library id, for membership checks. */
const KNOWN_IDS: ReadonlySet<string> = new Set(LIBRARY_EQUIPMENT.map((m) => m.id));

/**
 * The library machine that stands for this `machine_type`, or null when none
 * does.
 *
 * Null is a real answer: the viewer then opens on the library's first machine
 * with all 48 still reachable, rather than pretending an unmapped type is
 * something it is not.
 */
export function libraryIdForMachineType(machineType: string | null | undefined): string | null {
  if (!machineType) return null;
  const id = LIBRARY_ID_BY_MACHINE_TYPE[machineType.trim().toLowerCase()];
  return id && KNOWN_IDS.has(id) ? id : null;
}

/** The full entry for a library id, or null when the id is not one of ours. */
export function libraryModel(id: string | null | undefined): LibraryModel | null {
  if (!id) return null;
  return LIBRARY_EQUIPMENT.find((m) => m.id === id) ?? null;
}

/** The machine types this map covers, for tests and for documentation. */
export const MAPPED_MACHINE_TYPES: readonly string[] = Object.freeze(
  Object.keys(LIBRARY_ID_BY_MACHINE_TYPE)
);

import type { SensorListItem } from "@/api/sensorExport";
import type { EquipmentHealth, EquipmentHealthStatus } from "@/types/dashboard";

/**
 * The Plant → Area → Line → Machine → Sensor tree.
 *
 * Both halves of it already exist server-side and neither knows about the
 * other: `/api/v1/sensors` carries the location columns on every sensor row,
 * and `/api/v1/dashboard/summary` grades each machine. This joins them on
 * `equipment_id` so one walk of the tree can show both where a sensor sits and
 * what condition its machine is in.
 *
 * The same shape drives the cascading filter bar and the browsable tree, so the
 * two can never disagree about what exists under a plant.
 */

export type HierarchyLevel = "plant" | "area" | "line" | "machine" | "sensor";

/** Worst-first ranking for rolling a child's status up to its parent. */
const STATUS_SEVERITY: Record<EquipmentHealthStatus, number> = {
  critical: 4,
  warning: 3,
  no_baseline: 2,
  no_data: 1,
  normal: 0,
};

export function worstStatus(
  statuses: EquipmentHealthStatus[]
): EquipmentHealthStatus {
  let worst: EquipmentHealthStatus = "no_data";
  let rank = -1;
  for (const status of statuses) {
    const severity = STATUS_SEVERITY[status] ?? 0;
    if (severity > rank) {
      rank = severity;
      worst = status;
    }
  }
  return worst;
}

export interface HierarchySensorNode {
  kind: "sensor";
  id: string;
  label: string;
  detail: string;
  sensor: SensorListItem;
  /** Inherited from the machine — grading is per machine, not per sensor. */
  status: EquipmentHealthStatus;
}

export interface HierarchyMachineNode {
  kind: "machine";
  id: string;
  label: string;
  machineId: string | null;
  machineType: string;
  status: EquipmentHealthStatus;
  healthScore: number | null;
  lastUploadAt: string | null;
  sensors: HierarchySensorNode[];
}

export interface HierarchyLineNode {
  kind: "line";
  id: string;
  label: string;
  status: EquipmentHealthStatus;
  machines: HierarchyMachineNode[];
}

export interface HierarchyAreaNode {
  kind: "area";
  id: string;
  label: string;
  status: EquipmentHealthStatus;
  lines: HierarchyLineNode[];
}

export interface HierarchyPlantNode {
  kind: "plant";
  id: string;
  label: string;
  status: EquipmentHealthStatus;
  areas: HierarchyAreaNode[];
}

export interface HierarchyCounts {
  plants: number;
  areas: number;
  lines: number;
  machines: number;
  sensors: number;
}

export interface SensorHierarchy {
  plants: HierarchyPlantNode[];
  counts: HierarchyCounts;
  /** Machine-level status tally, for the fleet strip above the tree. */
  statusCounts: Record<EquipmentHealthStatus, number>;
}

/** A blank level reads as a gap in the master data, not as an empty string. */
const UNASSIGNED = "Unassigned";

function labelOrUnassigned(value: string | null | undefined): string {
  const trimmed = (value ?? "").trim();
  return trimmed.length ? trimmed : UNASSIGNED;
}

export function sensorNodeLabel(sensor: SensorListItem): string {
  const location = labelOrUnassigned(sensor.mounting_location);
  const orientation = (sensor.orientation ?? "").trim();
  return orientation ? `${location} (${orientation})` : location;
}

function emptyStatusCounts(): Record<EquipmentHealthStatus, number> {
  return { critical: 0, warning: 0, normal: 0, no_baseline: 0, no_data: 0 };
}

/**
 * Group the flat sensor list into the tree, grading each machine from the
 * dashboard summary.
 *
 * A machine the summary does not mention is `no_data` rather than absent: a
 * sensor that exists but has never been uploaded to is exactly what an operator
 * opening this page is looking for.
 */
export function buildSensorHierarchy(
  sensors: SensorListItem[],
  equipmentHealth: EquipmentHealth[]
): SensorHierarchy {
  const healthByEquipment = new Map<string, EquipmentHealth>();
  for (const item of equipmentHealth) {
    healthByEquipment.set(item.equipment_id, item);
  }

  // Nested maps keep insertion cheap; the tree is sorted once at the end.
  const plants = new Map<string, Map<string, Map<string, Map<string, HierarchyMachineNode>>>>();
  const counts: HierarchyCounts = { plants: 0, areas: 0, lines: 0, machines: 0, sensors: 0 };
  const statusCounts = emptyStatusCounts();

  for (const sensor of sensors) {
    const plantKey = labelOrUnassigned(sensor.plant_name);
    const areaKey = labelOrUnassigned(sensor.area);
    const lineKey = labelOrUnassigned(sensor.line);

    let areas = plants.get(plantKey);
    if (!areas) {
      areas = new Map();
      plants.set(plantKey, areas);
    }
    let lines = areas.get(areaKey);
    if (!lines) {
      lines = new Map();
      areas.set(areaKey, lines);
    }
    let machines = lines.get(lineKey);
    if (!machines) {
      machines = new Map();
      lines.set(lineKey, machines);
    }

    let machine = machines.get(sensor.equipment_id);
    if (!machine) {
      const health = healthByEquipment.get(sensor.equipment_id);
      const status: EquipmentHealthStatus = health?.status ?? "no_data";
      machine = {
        kind: "machine",
        id: sensor.equipment_id,
        label: labelOrUnassigned(sensor.machine_name),
        machineId: sensor.machine_id,
        machineType: labelOrUnassigned(sensor.machine_type),
        status,
        healthScore: health?.health_score ?? null,
        lastUploadAt: health?.last_upload_at ?? null,
        sensors: [],
      };
      machines.set(sensor.equipment_id, machine);
      statusCounts[status] += 1;
      counts.machines += 1;
    }

    machine.sensors.push({
      kind: "sensor",
      id: sensor.sensor_id,
      label: sensorNodeLabel(sensor),
      detail: labelOrUnassigned(sensor.sensor_type),
      sensor,
      status: machine.status,
    });
    counts.sensors += 1;
  }

  const byLabel = <T extends { label: string }>(a: T, b: T) => a.label.localeCompare(b.label);

  const plantNodes: HierarchyPlantNode[] = [...plants.entries()]
    .map(([plantLabel, areas]) => {
      const areaNodes: HierarchyAreaNode[] = [...areas.entries()]
        .map(([areaLabel, lines]) => {
          const lineNodes: HierarchyLineNode[] = [...lines.entries()]
            .map(([lineLabel, machines]) => {
              const machineNodes = [...machines.values()]
                .map((machine) => ({ ...machine, sensors: [...machine.sensors].sort(byLabel) }))
                .sort(byLabel);
              counts.lines += 1;
              return {
                kind: "line" as const,
                id: `${plantLabel}//${areaLabel}//${lineLabel}`,
                label: lineLabel,
                status: worstStatus(machineNodes.map((m) => m.status)),
                machines: machineNodes,
              };
            })
            .sort(byLabel);
          counts.areas += 1;
          return {
            kind: "area" as const,
            id: `${plantLabel}//${areaLabel}`,
            label: areaLabel,
            status: worstStatus(lineNodes.map((l) => l.status)),
            lines: lineNodes,
          };
        })
        .sort(byLabel);
      counts.plants += 1;
      return {
        kind: "plant" as const,
        id: plantLabel,
        label: plantLabel,
        status: worstStatus(areaNodes.map((a) => a.status)),
        areas: areaNodes,
      };
    })
    .sort(byLabel);

  return { plants: plantNodes, counts, statusCounts };
}

export interface HierarchySelection {
  plant: string;
  area: string;
  line: string;
  machineId: string;
  sensorId: string;
}

export const EMPTY_SELECTION: HierarchySelection = {
  plant: "",
  area: "",
  line: "",
  machineId: "",
  sensorId: "",
};

export function sameSelection(a: HierarchySelection, b: HierarchySelection): boolean {
  return (
    a.plant === b.plant &&
    a.area === b.area &&
    a.line === b.line &&
    a.machineId === b.machineId &&
    a.sensorId === b.sensorId
  );
}

/** The nodes the current selection resolves to, as far as it goes. */
export interface ResolvedPath {
  plant: HierarchyPlantNode | null;
  area: HierarchyAreaNode | null;
  line: HierarchyLineNode | null;
  machine: HierarchyMachineNode | null;
  sensor: HierarchySensorNode | null;
}

export function resolvePath(
  hierarchy: SensorHierarchy,
  selection: HierarchySelection
): ResolvedPath {
  const plant = hierarchy.plants.find((p) => p.label === selection.plant) ?? null;
  const area = plant?.areas.find((a) => a.label === selection.area) ?? null;
  const line = area?.lines.find((l) => l.label === selection.line) ?? null;
  const machine = line?.machines.find((m) => m.id === selection.machineId) ?? null;
  const sensor = machine?.sensors.find((s) => s.id === selection.sensorId) ?? null;
  return { plant, area, line, machine, sensor };
}

/** The options offered at each level, given everything chosen above it. */
export interface HierarchyOptions {
  plants: HierarchyPlantNode[];
  areas: HierarchyAreaNode[];
  lines: HierarchyLineNode[];
  machines: HierarchyMachineNode[];
  sensors: HierarchySensorNode[];
}

export function hierarchyOptions(
  hierarchy: SensorHierarchy,
  selection: HierarchySelection
): HierarchyOptions {
  const path = resolvePath(hierarchy, selection);
  return {
    plants: hierarchy.plants,
    areas: path.plant?.areas ?? [],
    lines: path.area?.lines ?? [],
    machines: path.line?.machines ?? [],
    sensors: path.machine?.sensors ?? [],
  };
}

const LEVEL_ORDER: HierarchyLevel[] = ["plant", "area", "line", "machine", "sensor"];

/**
 * Set one level and clear everything below it.
 *
 * Keeping a machine selected while its plant changes is how a filter bar ends
 * up analysing an asset that is no longer in any of its own dropdowns.
 */
export function selectLevel(
  selection: HierarchySelection,
  level: HierarchyLevel,
  value: string
): HierarchySelection {
  const next = { ...selection };
  const from = LEVEL_ORDER.indexOf(level);

  for (let i = from; i < LEVEL_ORDER.length; i += 1) {
    const key = LEVEL_ORDER[i];
    const assigned = i === from ? value : "";
    if (key === "plant") next.plant = assigned;
    else if (key === "area") next.area = assigned;
    else if (key === "line") next.line = assigned;
    else if (key === "machine") next.machineId = assigned;
    else next.sensorId = assigned;
  }

  return next;
}

/** The full path down to one sensor, for a click in the tree. */
export function selectionForSensor(
  hierarchy: SensorHierarchy,
  sensorId: string
): HierarchySelection | null {
  for (const plant of hierarchy.plants) {
    for (const area of plant.areas) {
      for (const line of area.lines) {
        for (const machine of line.machines) {
          const sensor = machine.sensors.find((s) => s.id === sensorId);
          if (sensor) {
            return {
              plant: plant.label,
              area: area.label,
              line: line.label,
              machineId: machine.id,
              sensorId: sensor.id,
            };
          }
        }
      }
    }
  }
  return null;
}

/**
 * Drop selections the tree no longer contains, then walk down through every
 * level that has exactly one option and pick it.
 *
 * Five dropdowns is a lot of clicking to reach a site with one plant and one
 * machine on it, and a level offering a single choice is not a decision.
 */
export function normalizeSelection(
  hierarchy: SensorHierarchy,
  selection: HierarchySelection
): HierarchySelection {
  let next = { ...selection };

  if (next.plant && !hierarchy.plants.some((p) => p.label === next.plant)) {
    next = selectLevel(next, "plant", "");
  }
  if (!next.plant && hierarchy.plants.length === 1) {
    next = selectLevel(next, "plant", hierarchy.plants[0].label);
  }

  const plant = hierarchy.plants.find((p) => p.label === next.plant);
  if (!plant) return next;

  if (next.area && !plant.areas.some((a) => a.label === next.area)) {
    next = selectLevel(next, "area", "");
  }
  if (!next.area && plant.areas.length === 1) {
    next = selectLevel(next, "area", plant.areas[0].label);
  }

  const area = plant.areas.find((a) => a.label === next.area);
  if (!area) return next;

  if (next.line && !area.lines.some((l) => l.label === next.line)) {
    next = selectLevel(next, "line", "");
  }
  if (!next.line && area.lines.length === 1) {
    next = selectLevel(next, "line", area.lines[0].label);
  }

  const line = area.lines.find((l) => l.label === next.line);
  if (!line) return next;

  if (next.machineId && !line.machines.some((m) => m.id === next.machineId)) {
    next = selectLevel(next, "machine", "");
  }
  if (!next.machineId && line.machines.length === 1) {
    next = selectLevel(next, "machine", line.machines[0].id);
  }

  const machine = line.machines.find((m) => m.id === next.machineId);
  if (!machine) return next;

  if (next.sensorId && !machine.sensors.some((s) => s.id === next.sensorId)) {
    next = selectLevel(next, "sensor", "");
  }
  if (!next.sensorId && machine.sensors.length === 1) {
    next = selectLevel(next, "sensor", machine.sensors[0].id);
  }

  return next;
}

import type { ThresholdRule, ThresholdScopeSensor } from "@/types/thresholds";

/**
 * Which rule a sensor is actually judged by, for one feature.
 *
 * The names are the scopes the backend resolves in order — sensor, then
 * machine, then machine type, then global. `none` means no rule exists for the
 * feature at any scope, so nothing grades it at all; that is not the same as
 * inheriting, and a view that showed them alike would report an ungraded
 * feature as a configured one.
 */
export type ThresholdScopeLevel = "sensor" | "machine" | "machine_type" | "global" | "none";

/** True for the levels where the sensor is borrowing a broader rule. */
export function isInherited(level: ThresholdScopeLevel): boolean {
  return level === "machine" || level === "machine_type" || level === "global";
}

export interface SensorCoverageCell {
  level: ThresholdScopeLevel;
  rule: ThresholdRule | null;
}

export interface SensorCoverageRow {
  sensor: ThresholdScopeSensor;
  /** Keyed by feature code. */
  cells: Record<string, SensorCoverageCell>;
  /** How many features this sensor has a limit of its very own for. */
  ownCount: number;
}

export interface SensorCoverageSummary {
  rows: SensorCoverageRow[];
  /** Sensors with at least one limit of their own. */
  sensorsWithOwnLimits: number;
  totalSensors: number;
}

function isGlobal(rule: ThresholdRule): boolean {
  return (
    rule.sensor_id === null &&
    rule.equipment_id === null &&
    (rule.machine_type === null || rule.machine_type.trim() === "")
  );
}

/**
 * Machine type is compared without case or surrounding space.
 *
 * Nothing canonicalises it: the equipment records say "Pump" and "Wind
 * Turbine", while a rule's machine type is free text somebody typed. The
 * backend resolver compares them the same way, and a view that compared them
 * exactly would show a sensor falling back to global while the engine was in
 * fact applying the machine-type rule — the screen would disagree with the
 * alarm.
 */
function sameMachineType(a: string | null, b: string | null): boolean {
  if (!a || !b) return false;
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/**
 * Resolve, for every sensor and every feature, which scope's limit applies.
 *
 * This mirrors `get_resolved_rule_map` in the backend rather than inventing a
 * second opinion. It deliberately ignores `channel`: the question here is which
 * *scope* owns a sensor's limit, and a per-channel row inside a scope does not
 * change that answer. Channel coverage is the other half of the matrix.
 */
export function buildSensorCoverage(
  rules: ThresholdRule[],
  sensors: ThresholdScopeSensor[],
  featureCodes: string[]
): SensorCoverageSummary {
  const bySensor = new Map<string, ThresholdRule>();
  const byEquipment = new Map<string, ThresholdRule>();
  const byMachineType: { type: string; rule: ThresholdRule }[] = [];
  const globals = new Map<string, ThresholdRule>();

  for (const rule of rules) {
    const code = rule.feature_code;
    if (rule.sensor_id) {
      const key = `${rule.sensor_id}:${code}`;
      if (!bySensor.has(key)) bySensor.set(key, rule);
    } else if (rule.equipment_id) {
      const key = `${rule.equipment_id}:${code}`;
      if (!byEquipment.has(key)) byEquipment.set(key, rule);
    } else if (rule.machine_type && rule.machine_type.trim() !== "") {
      byMachineType.push({ type: rule.machine_type, rule });
    } else if (isGlobal(rule) && !globals.has(code)) {
      globals.set(code, rule);
    }
  }

  const rows: SensorCoverageRow[] = sensors.map((sensor) => {
    const cells: Record<string, SensorCoverageCell> = {};
    let ownCount = 0;

    for (const code of featureCodes) {
      const own = bySensor.get(`${sensor.id}:${code}`);
      if (own) {
        cells[code] = { level: "sensor", rule: own };
        ownCount += 1;
        continue;
      }

      const machine = sensor.equipment_id
        ? byEquipment.get(`${sensor.equipment_id}:${code}`)
        : undefined;
      if (machine) {
        cells[code] = { level: "machine", rule: machine };
        continue;
      }

      const typed = byMachineType.find(
        (entry) => entry.rule.feature_code === code && sameMachineType(entry.type, sensor.machine_type)
      );
      if (typed) {
        cells[code] = { level: "machine_type", rule: typed.rule };
        continue;
      }

      const fallback = globals.get(code) ?? null;
      cells[code] = { level: fallback ? "global" : "none", rule: fallback };
    }

    return { sensor, cells, ownCount };
  });

  return {
    rows,
    sensorsWithOwnLimits: rows.filter((row) => row.ownCount > 0).length,
    totalSensors: rows.length,
  };
}

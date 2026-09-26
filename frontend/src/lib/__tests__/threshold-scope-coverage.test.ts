import { describe, expect, it } from "vitest";
import {
  buildSensorCoverage,
  isInherited,
  type ThresholdScopeLevel,
} from "@/lib/threshold-scope-coverage";
import type { ThresholdRule, ThresholdScopeSensor } from "@/types/thresholds";

const SENSOR = "11111111-1111-1111-1111-111111111111";
const OTHER_SENSOR = "22222222-2222-2222-2222-222222222222";
const MACHINE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const OTHER_MACHINE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

function rule(over: Partial<ThresholdRule> = {}): ThresholdRule {
  return {
    id: Math.random().toString(36).slice(2),
    feature_code: "rms",
    feature_name: "RMS",
    unit: "g",
    rule_type: "absolute_max",
    machine_type: null,
    channel: null,
    sensor_id: null,
    equipment_id: null,
    normal_max: 0.01,
    warning_max: 0.02,
    normal_min: null,
    warning_min: null,
    metadata: {},
    is_active: true,
    updated_at: null,
    updated_by: null,
    is_default: true,
    limit_labels: {},
    ...over,
  };
}

function sensor(over: Partial<ThresholdScopeSensor> = {}): ThresholdScopeSensor {
  return {
    id: SENSOR,
    label: "Boiler Feed Motor — Motor DE · Horizontal",
    machine_name: "Boiler Feed Motor",
    machine_type: "Pump",
    equipment_id: MACHINE,
    ...over,
  };
}

function levelFor(rules: ThresholdRule[], sensors: ThresholdScopeSensor[]): ThresholdScopeLevel {
  const { rows } = buildSensorCoverage(rules, sensors, ["rms"]);
  return rows[0].cells.rms.level;
}

describe("buildSensorCoverage", () => {
  it("reports a sensor's own limit as its own", () => {
    expect(levelFor([rule(), rule({ sensor_id: SENSOR })], [sensor()])).toBe("sensor");
  });

  it("reports a sensor with no rule of its own as falling back to global", () => {
    expect(levelFor([rule()], [sensor()])).toBe("global");
  });

  it("names the machine rule rather than calling it global", () => {
    // The ticket asks which sensors fall back to *the global one*. A sensor
    // covered by its machine's rule is not one of them, and saying so is the
    // difference between describing the configuration and describing the
    // machine.
    expect(levelFor([rule(), rule({ equipment_id: MACHINE })], [sensor()])).toBe("machine");
  });

  it("names the machine-type rule", () => {
    expect(levelFor([rule(), rule({ machine_type: "Pump" })], [sensor()])).toBe("machine_type");
  });

  it("follows the same ladder the backend resolves", () => {
    const all = [
      rule(),
      rule({ machine_type: "Pump" }),
      rule({ equipment_id: MACHINE }),
      rule({ sensor_id: SENSOR }),
    ];
    expect(levelFor(all, [sensor()])).toBe("sensor");
    expect(levelFor(all.slice(0, 3), [sensor()])).toBe("machine");
    expect(levelFor(all.slice(0, 2), [sensor()])).toBe("machine_type");
    expect(levelFor(all.slice(0, 1), [sensor()])).toBe("global");
  });

  it("matches machine type whatever case either side used", () => {
    // The equipment records say "Pump"; a rule is free text. The backend
    // compares these without case, so a screen that compared them exactly
    // would show a fallback while the engine applied the pump rule.
    for (const typed of ["pump", "PUMP", "  Pump  "]) {
      expect(levelFor([rule(), rule({ machine_type: typed })], [sensor()])).toBe("machine_type");
    }
  });

  it("does not apply another machine's rule to this sensor", () => {
    const rules = [
      rule(),
      rule({ sensor_id: OTHER_SENSOR }),
      rule({ equipment_id: OTHER_MACHINE }),
      rule({ machine_type: "Compressor" }),
    ];
    expect(levelFor(rules, [sensor()])).toBe("global");
  });

  it("distinguishes a feature nothing grades from one that is inherited", () => {
    const { rows } = buildSensorCoverage([], [sensor()], ["rms"]);
    expect(rows[0].cells.rms.level).toBe("none");
    expect(rows[0].cells.rms.rule).toBeNull();
  });

  it("counts how many sensors carry limits of their own", () => {
    const sensors = [
      sensor(),
      sensor({ id: OTHER_SENSOR, equipment_id: OTHER_MACHINE, machine_type: "Blower" }),
    ];
    const summary = buildSensorCoverage(
      [rule(), rule({ sensor_id: SENSOR })],
      sensors,
      ["rms"]
    );

    expect(summary.totalSensors).toBe(2);
    expect(summary.sensorsWithOwnLimits).toBe(1);
    expect(summary.rows[0].ownCount).toBe(1);
    expect(summary.rows[1].ownCount).toBe(0);
  });

  it("keeps a per-channel row from changing which scope owns the limit", () => {
    // Channel is the other axis of the matrix. A sensor rule that names a
    // channel is still a sensor rule.
    expect(levelFor([rule(), rule({ sensor_id: SENSOR, channel: 3 })], [sensor()])).toBe("sensor");
  });

  it("treats a sensor with no equipment as falling back", () => {
    const orphan = sensor({ equipment_id: null, machine_type: null });
    expect(levelFor([rule(), rule({ equipment_id: MACHINE })], [orphan])).toBe("global");
  });
});

describe("isInherited", () => {
  it("counts every borrowed scope and nothing else", () => {
    expect(isInherited("machine")).toBe(true);
    expect(isInherited("machine_type")).toBe(true);
    expect(isInherited("global")).toBe(true);
    expect(isInherited("sensor")).toBe(false);
    // Nothing grades it, so there is nothing to inherit.
    expect(isInherited("none")).toBe(false);
  });
});

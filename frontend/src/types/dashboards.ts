/**
 * Section 19's three dashboards, and section 12.2's reliability score.
 *
 * Written from the endpoints' recorded responses. Every `| null` is a case
 * the platform could not work out and the screen has to say so in words —
 * `health: null` is not 100, `temperature_c: null` is not cold, and
 * `false_alarm_rate: null` is not zero.
 */

/** Section 19.1 — one machine as an operator needs it. */
export interface OperatorMachine {
  equipment_id: string;
  machine_name: string;
  plant_name: string | null;
  area: string | null;
  sensor_id: string | null;
  running_state: string;
  rms_g: number | null;
  /** Always null: nothing on this platform measures a temperature. */
  temperature_c: number | null;
  temperature_note: string;
  alarms: number;
  worst_alarm_band: string | null;
  status: "ok" | "watch" | "attention" | "no_data";
  /** One short sentence. This screen is read while walking. */
  action: string;
  last_seen: string | null;
}

export interface OperatorResponse {
  machines: OperatorMachine[];
  counts: {
    total: number;
    attention: number;
    watch: number;
    ok: number;
    no_data: number;
  };
  temperature_available: boolean;
  reason: string;
}

/** Section 12.2 — how dependable a machine's record is. */
export interface ReliabilityFactor {
  key: string;
  name: string;
  penalty: number;
  points_off: number;
  reason: string;
  detail: Record<string, unknown>;
}

export interface ReliabilityResponse {
  score: number | null;
  band: string;
  ceiling: number;
  /** False while the record is too short to be evidence. */
  proven: boolean;
  usable: boolean;
  criticality: string | null;
  factors: ReliabilityFactor[];
  unknowns: string[];
  reason: string;
  sensor_id: string;
  captures: number;
  history_days: number | null;
  machine_name?: string | null;
}

/** Section 19.3 — one machine's row on the management view. */
export interface FleetMachine {
  equipment_id: string;
  machine_name: string;
  plant_name: string | null;
  area: string | null;
  criticality: string | null;
  sensor_id: string | null;
  health: number | null;
  health_band: string;
  health_ceiling?: number | null;
  data_quality?: string | null;
  reliability: number | null;
  reliability_band: string;
  reliability_proven?: boolean;
  open_findings: number;
  worst_stage: string | null;
  reason: string;
}

export interface AlarmQuality {
  judged: number;
  confirmed: number;
  rejected: number;
  /** Share of analyst verdicts that rejected a finding. Rises when the
   *  platform is wrong, which is the point. */
  false_alarm_rate: number | null;
  trend: "improving" | "worsening" | "flat" | null;
  reason: string;
}

export interface MaintenanceStatus {
  by_status: Record<string, number>;
  unassigned: number;
  repairs_confirmed: number;
  reason: string;
}

export interface FleetResponse {
  plant_name: string | null;
  machines: FleetMachine[];
  most_at_risk: FleetMachine[];
  counts: {
    machines: number;
    scored: number;
    unmeasured: number;
    critical_alarms: number;
    open_findings: number;
    under_watch: number;
  };
  /** Averaged over scored machines only; `unmeasured_machines` names the rest. */
  site_health_score: number | null;
  site_reliability_score: number | null;
  unmeasured_machines: string[];
  feedback: AlarmQuality;
  maintenance: MaintenanceStatus;
  reason: string;
}

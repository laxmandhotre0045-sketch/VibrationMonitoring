/** Industrial guidance, machine specs, and criticality definitions — client-side only */

export const CRITICALITY_IMPACT: Record<string, { label: string; color: string; bg: string; border: string; impact: string }> = {
  Low: {
    label: "LOW",
    color: "text-machine-healthy",
    bg: "bg-machine-healthy/10",
    border: "border-machine-healthy/30",
    impact: "Failure has minimal production impact. Standard monitoring interval applies.",
  },
  Medium: {
    label: "MEDIUM",
    color: "text-yellow-600",
    bg: "bg-yellow-50",
    border: "border-yellow-300",
    impact: "Failure may affect line efficiency. Enhanced vibration trending recommended.",
  },
  High: {
    label: "HIGH",
    color: "text-orange-600",
    bg: "bg-orange-50",
    border: "border-orange-300",
    impact: "Failure will disrupt production. Continuous condition monitoring required.",
  },
  Critical: {
    label: "CRITICAL",
    color: "text-machine-critical",
    bg: "bg-machine-critical/10",
    border: "border-machine-critical/30",
    impact: "Unexpected failure may stop production. Priority AI diagnostics and PM scheduling.",
  },
};

export const FIELD_HINTS: Record<string, string> = {
  plant_name: "Defines asset hierarchy for fleet-wide reliability reporting and alarm routing.",
  area: "Used to group assets by functional area for condition-based maintenance planning.",
  line: "Production line association enables downtime correlation with vibration events.",
  machine_name: "Human-readable identifier displayed on dashboards and work orders.",
  machine_id: "Unique asset code used across CMMS, historian, and sensor data streams.",
  machine_type: "Determines diagnostic algorithms, fault libraries, and expected sensor layout.",
  machine_criticality: "Drives monitoring frequency, alert thresholds, and maintenance priority.",
  rated_rpm: "Used to calculate shaft frequency and bearing defect frequencies.",
  rated_power_kw: "Correlates vibration amplitude with load conditions for baseline normalization.",
  drive_type: "Affects expected vibration signatures and coupling fault patterns.",
  bearing_number_de: "Required for automatic bearing fault analysis and BPFO/BPFI calculation.",
  bearing_number_nde: "NDE bearing mapping enables dual-bearing defect frequency tracking.",
  bearing_details: "Bearing specification supports fault library matching and lubrication analysis.",
  operating_speed_min: "Lower bound for operating envelope and alarm band configuration.",
  operating_speed_max: "Upper bound used for order tracking and variable-speed diagnostics.",
  sensor_type: "Sensor type determines sampling parameters and analysis methodology (FFT/envelope).",
  mounting_location: "Mounting point selection affects which failure modes are detectable.",
  orientation: "Impacts vibration spectrum interpretation — axial vs radial fault sensitivity.",
};

export const COMPLETENESS_SECTIONS = [
  { id: 1, label: "Basic Details", key: "basic" },
  { id: 2, label: "Mechanical Details", key: "mechanical" },
  { id: 3, label: "Rotating Components", key: "rotating" },
  { id: 4, label: "Operating Conditions", key: "operating" },
  { id: 5, label: "Sensor Mapping", key: "sensors" },
] as const;

export const MACHINE_SPECS: Record<string, { sensors: string[]; bearings: string[]; description: string }> = {
  Pump: {
    description: "Centrifugal or positive displacement pump",
    sensors: ["DE Horizontal", "DE Vertical", "DE Axial", "NDE Horizontal"],
    bearings: ["Impeller DE", "Impeller NDE", "Motor DE", "Motor NDE"],
  },
  Motor: {
    description: "Electric motor drive unit",
    sensors: ["DE Horizontal", "DE Vertical", "DE Axial", "NDE Horizontal", "NDE Axial"],
    bearings: ["Drive End (DE)", "Non-Drive End (NDE)"],
  },
  Fan: {
    description: "Industrial fan or blower assembly",
    sensors: ["Bearing Housing DE", "Bearing Housing NDE", "Motor DE"],
    bearings: ["Fan DE", "Fan NDE", "Motor Bearings"],
  },
  Blower: {
    description: "High-volume air movement equipment",
    sensors: ["Bearing Housing DE", "Bearing Housing NDE", "Motor DE"],
    bearings: ["Blower DE", "Blower NDE"],
  },
  Compressor: {
    description: "Air or gas compression system",
    sensors: ["DE Horizontal", "DE Vertical", "NDE Horizontal", "NDE Axial"],
    bearings: ["Compressor DE", "Compressor NDE", "Motor DE"],
  },
  Gearbox: {
    description: "Speed reduction or increase gearbox",
    sensors: ["Input Shaft", "Output Shaft", "Housing"],
    bearings: ["Input Bearing", "Output Bearing", "Intermediate"],
  },
  Turbine: {
    description: "Steam or gas turbine rotor",
    sensors: ["Bearing DE", "Bearing NDE", "Casing"],
    bearings: ["Turbine DE", "Turbine NDE"],
  },
  Generator: {
    description: "Electrical power generation unit",
    sensors: ["DE Horizontal", "DE Vertical", "NDE Horizontal"],
    bearings: ["Generator DE", "Generator NDE"],
  },
  Conveyor: {
    description: "Material transport conveyor system",
    sensors: ["Drive Motor", "Tail Pulley", "Head Pulley"],
    bearings: ["Drive Bearing", "Idler Bearings"],
  },
  Crusher: {
    description: "Material crushing equipment",
    sensors: ["Main Bearing DE", "Main Bearing NDE", "Motor"],
    bearings: ["Crusher DE", "Crusher NDE"],
  },
  default: {
    description: "Industrial rotating equipment",
    sensors: ["DE Horizontal", "DE Vertical", "NDE Horizontal"],
    bearings: ["Drive End (DE)", "Non-Drive End (NDE)"],
  },
};

export const EMPTY_STATE_MESSAGES: Record<string, string> = {
  mechanical: "Configure machine specifications to unlock AI diagnostics.",
  rotating: "Bearing information required for fault library matching.",
  sensors: "Sensor mapping required for vibration analysis.",
  operating: "Operating envelope data required for baseline trending and alarm bands.",
  general: "Complete asset profile to enable FFT analysis, bearing fault detection, and predictive maintenance.",
};

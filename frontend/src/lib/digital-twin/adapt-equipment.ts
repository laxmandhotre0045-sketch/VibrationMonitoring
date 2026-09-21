/**
 * Digital Twin — the single adapter from saved equipment to viewer props.
 *
 * The backend returns sensors as `mounting_location` + `orientation` and
 * bearings as `bearing_number_de` / `_nde` (+ optional catalogue ids). There is
 * no `anchorNode` column and no channel column. Rather than change the schema,
 * this function derives both here:
 *
 *   mounting_location  --registry--> anchor id --> `CH_<LOCATION>_<AXIS>`
 *   bearing DE / NDE   --registry--> anchor id --> `BRG_<LOCATION>`
 *
 * Binding by location rather than by channel number matters: channel numbers
 * are positional, so deleting one sensor would otherwise re-point every marker
 * after it at the wrong part of the machine.
 *
 * If the backend ever wants to own this, the change is one nullable
 * `anchor_node` column on `sensor_configurations` plus two on
 * `equipment_masters`; nothing else here would move.
 */

import type { EquipmentFormData } from "@/types/equipment";
import { resolveTwin, type MountingRowInput } from "./twin-config";
import { bearingNodeName, resolveMachineTypeId, sensorNodeName } from "./machine-type-map";
import type { MachineTypeId, TwinBearing, TwinSensor } from "./types";

export interface TwinViewModel {
  machineType: MachineTypeId;
  /** Raw `machine_type`, for display — "DG Set" rather than "motor". */
  machineTypeLabel: string;
  machineName: string;
  bearings: TwinBearing[];
  sensors: TwinSensor[];
}

export function adaptEquipmentToTwin(
  data: EquipmentFormData,
  mountingRows: MountingRowInput[]
): TwinViewModel {
  const resolved = resolveTwin(data, mountingRows);

  const bearings: TwinBearing[] = [
    ...resolved.bearings.map((bearing) => ({
      id: bearingNodeName(bearing.anchor.id),
      name: bearing.anchor.label,
      note:
        bearing.bearingNumber ||
        (bearing.catalogId ? `Bearing ID ${bearing.catalogId}` : undefined),
      configured: true,
      anchorNode: bearingNodeName(bearing.anchor.id),
    })),
    // Positions the model has that the form has not filled in. Step 3 is
    // optional and stays that way: these draw as outlines, never as fitted
    // parts, and they are what make four bearing chips appear on a two-field
    // form.
    ...resolved.ghostBearingAnchors.map((anchor) => ({
      id: bearingNodeName(anchor.id),
      name: anchor.label,
      configured: false,
      anchorNode: bearingNodeName(anchor.id),
    })),
  ];

  const sensors: TwinSensor[] = resolved.sensors.map((sensor) => ({
    // The channel is the operator-facing identity and is unique per render,
    // which is what the side panel and the chips both key off.
    id: sensor.channel,
    axis: sensor.orientation as TwinSensor["axis"],
    location: sensor.mountingLocation,
    anchorNode: sensorNodeName(sensor.anchor.id, sensor.orientation),
    detail: sensor.sensorType ?? undefined,
    persisted: sensor.source === "sensor",
    // `status` is intentionally absent: the setup flow has no condition data.
    // Populate it here when it exists and the marker and chip colour follow.
  }));

  return {
    machineType: resolveMachineTypeId(data.machine_type),
    machineTypeLabel: (data.machine_type ?? "").trim(),
    machineName: (data.machine_name ?? "").trim(),
    bearings,
    sensors,
  };
}

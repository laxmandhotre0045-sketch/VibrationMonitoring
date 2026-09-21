/**
 * Digital Twin — turning the Equipment Master form into placed geometry.
 *
 * This is the whole mapping layer:
 *
 *   machine_type       → model            (machine-registry)
 *   bearing_number_*   → bearing anchor   (model.de/ndeBearingAnchorId)
 *   mounting_location  → sensor anchor    (model.mountingLocationMap)
 *   orientation        → direction vector (orientationDirection)
 *
 * Nothing here stores or needs coordinates: the form keeps the same logical
 * values it always has, and the position is derived every render. That is why
 * the feature needs no new database columns.
 */

import type { EquipmentFormData } from "@/types/equipment";
import { findBearingAnchor, findSensorAnchor, resolveMachineModel } from "./machine-registry";
import type {
  BearingAnchorSpec,
  MachineModelSpec,
  ResolvedBearing,
  ResolvedSensor,
  ResolvedTwin,
  SensorAnchorSpec,
  Vec3,
} from "./types";

/**
 * One row of the Step 5 "Sensor Mounting & Orientation" table.
 *
 * These six rows are UI state, not sensor records — they are not saved with
 * the equipment, and this feature does not change that. They are shown in the
 * twin because they are what the operator is configuring on that step.
 */
export interface MountingRowInput {
  label: string;
  mountingLocation: string;
  orientation: string;
}

const RAD_45 = Math.SQRT1_2;

function normalizeOrientation(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function add(point: Vec3, direction: Vec3, scale: number): Vec3 {
  return [
    point[0] + direction[0] * scale,
    point[1] + direction[1] * scale,
    point[2] + direction[2] * scale,
  ];
}

/**
 * The direction an orientation points, in the model's frame.
 *
 * Generated from the orientation rather than drawn per sensor, so a new
 * sensor or a changed orientation needs no new artwork.
 *
 *   Horizontal  across the shaft        →  +Z
 *   Vertical    up                      →  +Y
 *   Axial       along the shaft          →  ±X, away from the machine
 *   Radial      out from the shaft axis  →  45° in the YZ plane
 *   Tangential  tangent to rotation      →  perpendicular to both
 *
 * Radial and Tangential have no meaning on a static mounting point such as the
 * Foundation, where they fall back to the nearest sensible axis.
 */
export function orientationDirection(
  orientation: string | null | undefined,
  anchor: SensorAnchorSpec
): Vec3 {
  switch (normalizeOrientation(orientation)) {
    case "vertical":
      return [0, 1, 0];
    case "axial":
      return [anchor.axialSign, 0, 0];
    case "radial":
      return anchor.static ? [0, 1, 0] : [0, RAD_45, RAD_45];
    case "tangential":
      // cross(shaft axis, radial) — tangent to the direction of rotation.
      return anchor.static ? [0, 0, 1] : [0, -RAD_45, RAD_45];
    case "horizontal":
    default:
      return [0, 0, 1];
  }
}

/**
 * Where a foundation-mounted marker sits.
 *
 * The Foundation has no shaft to stand off from, so pushing the marker along
 * the orientation would bury it in the base plate or float it in mid-air.
 * Instead every foundation marker sits on top of the plate, spread apart by
 * orientation so several stay separately visible; the arrow still points the
 * real direction.
 */
function staticMarkerOffset(orientation: string | null | undefined): [number, number] {
  switch (normalizeOrientation(orientation)) {
    case "vertical":
      return [0, 0];
    case "horizontal":
      return [0, 0.95];
    case "axial":
      return [0.95, 0];
    case "radial":
      return [-0.7, 0.7];
    case "tangential":
      return [0.7, -0.7];
    default:
      return [0, 0];
  }
}

/**
 * Where the marker for one sensor sits on the machine surface.
 *
 * A vertical sensor ends up on top of the housing, a horizontal one on its
 * side and an axial one on the end face, all from one anchor definition.
 * `stackIndex` nudges apart two sensors configured at the same place with the
 * same orientation, so neither becomes unclickable behind the other.
 */
export function markerPosition(
  anchor: SensorAnchorSpec,
  orientation: string | null | undefined,
  direction: Vec3,
  stackIndex: number
): Vec3 {
  const stack = stackIndex * 0.28;

  if (anchor.static) {
    const [offsetX, offsetZ] = staticMarkerOffset(orientation);
    return [
      anchor.axisPoint[0] + offsetX + stack,
      anchor.axisPoint[1] + 0.16,
      anchor.axisPoint[2] + offsetZ,
    ];
  }

  if (normalizeOrientation(orientation) === "axial") {
    // On the end face, lifted clear of the shaft that comes through it.
    return [
      anchor.axialFace + anchor.axialSign * 0.16,
      anchor.axisPoint[1] + anchor.radius * 0.55,
      anchor.axisPoint[2] + stack,
    ];
  }

  const base = add(anchor.axisPoint, direction, anchor.radius + 0.1);
  return [base[0] + stack, base[1], base[2]];
}

/** Display channel label. Derived from position — nothing persists a channel. */
export function channelLabel(index: number): string {
  return `CH${index + 1}`;
}

/**
 * A key covering exactly the fields the twin draws from.
 *
 * `watch()` on the Equipment Master form emits a new object on every keystroke
 * in any of some sixty fields. Memoising the twin on this signature means
 * typing a serial number or a maintenance note does not tear down and rebuild
 * the whole 3D scene — only a change that the twin would actually show does.
 */
export function twinSignature(
  data: EquipmentFormData,
  mountingRows: MountingRowInput[]
): string {
  const sensors = (data.sensors ?? []).map(
    (sensor) =>
      `${sensor.mounting_location ?? ""}~${sensor.orientation ?? ""}~${sensor.sensor_type ?? ""}`
  );
  const rows = mountingRows.map(
    (row) => `${row.label}~${row.mountingLocation}~${row.orientation}`
  );

  return [
    data.machine_type ?? "",
    data.machine_name ?? "",
    data.bearing_number_de ?? "",
    data.bearing_number_nde ?? "",
    data.bearing_de_catalog_id ?? "",
    data.bearing_nde_catalog_id ?? "",
    rows.join("|"),
    sensors.join("|"),
  ].join("§");
}

function resolveSensorAnchor(
  model: MachineModelSpec,
  mountingLocation: string
): { anchor: SensorAnchorSpec; mapped: boolean } {
  const anchorId = model.mountingLocationMap[mountingLocation.trim()];
  const anchor = anchorId ? findSensorAnchor(model, anchorId) : null;
  if (anchor) return { anchor, mapped: true };

  // No equivalent part on this model — place it on the foundation and say so,
  // rather than implying the machine has a part it does not.
  const fallback =
    findSensorAnchor(model, model.fallbackAnchorId) ?? model.sensorAnchors[0];
  return { anchor: fallback, mapped: false };
}

function buildSensor(
  model: MachineModelSpec,
  index: number,
  input: {
    key: string;
    rowLabel: string;
    mountingLocation: string;
    orientation: string;
    sensorType: string | null;
    source: "mounting" | "sensor";
  },
  stackCounts: Map<string, number>
): ResolvedSensor {
  const { anchor, mapped } = resolveSensorAnchor(model, input.mountingLocation);
  const direction = orientationDirection(input.orientation, anchor);

  const stackKey = `${anchor.id}|${normalizeOrientation(input.orientation)}`;
  const stackIndex = stackCounts.get(stackKey) ?? 0;
  stackCounts.set(stackKey, stackIndex + 1);

  return {
    key: input.key,
    channel: channelLabel(index),
    rowLabel: input.rowLabel,
    mountingLocation: input.mountingLocation,
    orientation: input.orientation,
    sensorType: input.sensorType,
    source: input.source,
    anchor,
    mapped,
    markerPosition: markerPosition(anchor, input.orientation, direction, stackIndex),
    direction,
  };
}

function buildBearing(
  model: MachineModelSpec,
  position: "DE" | "NDE",
  bearingNumber: string | null | undefined,
  catalogId: number | null | undefined
): ResolvedBearing | null {
  const number = (bearingNumber ?? "").trim();
  // A catalogue match with no typed number still counts as configured.
  if (!number && !catalogId) return null;

  const anchorId =
    position === "DE" ? model.deBearingAnchorId : model.ndeBearingAnchorId;
  const anchor = findBearingAnchor(model, anchorId);
  if (!anchor) return null;

  return {
    key: `bearing-${position}`,
    position,
    anchor,
    bearingNumber: number,
    catalogId: catalogId ?? null,
  };
}

/**
 * Everything the viewer needs, for the configuration as it stands right now.
 *
 * Pure and cheap — safe to recompute on every keystroke, which is what makes
 * the twin track the form live.
 */
export function resolveTwin(
  data: EquipmentFormData,
  mountingRows: MountingRowInput[]
): ResolvedTwin {
  const model = resolveMachineModel(data.machine_type);

  const bearings = [
    buildBearing(model, "DE", data.bearing_number_de, data.bearing_de_catalog_id),
    buildBearing(model, "NDE", data.bearing_number_nde, data.bearing_nde_catalog_id),
  ].filter((bearing): bearing is ResolvedBearing => bearing !== null);

  // Every bearing position the model has, minus the ones the form filled in.
  // The whole anchor set, not just the DE/NDE pair: a fan train carries four
  // bearings (motor DE/NDE and fan DE/NDE) while Step 3 captures two, so the
  // other two must still be visible as unconfigured positions rather than
  // vanishing the moment the first two are entered.
  const configuredAnchorIds = new Set(bearings.map((bearing) => bearing.anchor.id));
  const ghostBearingAnchors: BearingAnchorSpec[] = model.bearingAnchors.filter(
    (anchor) => !configuredAnchorIds.has(anchor.id)
  );

  const stackCounts = new Map<string, number>();
  const sensors: ResolvedSensor[] = [];

  // The six standard mounting rows come first, then anything added under
  // Additional Sensors — which is the order they read in on Step 5.
  mountingRows.forEach((row) => {
    if (!row.mountingLocation || !row.orientation) return;
    sensors.push(
      buildSensor(
        model,
        sensors.length,
        {
          key: `mounting-${row.label}`,
          rowLabel: row.label,
          mountingLocation: row.mountingLocation,
          orientation: row.orientation,
          sensorType: null,
          source: "mounting",
        },
        stackCounts
      )
    );
  });

  (data.sensors ?? []).forEach((sensor, index) => {
    if (!sensor.mounting_location || !sensor.orientation) return;
    sensors.push(
      buildSensor(
        model,
        sensors.length,
        {
          key: `sensor-${index}`,
          rowLabel: `Sensor ${index + 1}`,
          mountingLocation: sensor.mounting_location,
          orientation: sensor.orientation,
          sensorType: sensor.sensor_type || null,
          source: "sensor",
        },
        stackCounts
      )
    );
  });

  return {
    model,
    machineType: (data.machine_type ?? "").trim(),
    machineName: (data.machine_name ?? "").trim(),
    bearings,
    ghostBearingAnchors,
    sensors,
  };
}

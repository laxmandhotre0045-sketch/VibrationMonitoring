import api from "./client";

export interface SensorListItem {
  sensor_id: string;
  device_id: string | null;
  mounting_location: string;
  orientation: string;
  sensor_type: string;
  is_active: boolean;
  equipment_id: string;
  machine_name: string;
  machine_id: string | null;
  machine_type: string;
  plant_name: string;
  area: string;
  line: string;
}

export interface SensorExportRow {
  sensor_id: string;
  machine_name: string;
  upload_id: string;
  source: string;
  original_filename: string;
  observed_at: string;
  measured_at: string;
  created_at: string;
  rotation_speed_rpm: number | "";
  sample_count: number | "";
  channel_count: number | "";
  channel: number | "";
  feature_code: string;
  feature_name: string;
  value: number | "";
  unit: string;
  status: string;
  computed_at: string;
}

export interface SensorExportSummary {
  sensor_id: string;
  machine_name: string;
  machine_id: string | null;
  mounting_location: string;
  orientation: string;
  plant_name: string;
  area: string;
  line: string;
  captures_exported: number;
  captures_available: number;
  truncated: boolean;
  csv_rows: number;
  channels: number[];
  feature_codes: string[];
  status_counts: Record<string, number>;
  first_observed_at: string | null;
  last_observed_at: string | null;
  generated_at: string;
}

export interface SensorExport {
  summary: SensorExportSummary;
  rows: SensorExportRow[];
}

export async function listSensors(filterText = ""): Promise<SensorListItem[]> {
  const { data } = await api.get<{ count: number; items: SensorListItem[] }>(
    "/api/v1/sensors",
    { params: filterText ? { filter_text: filterText } : undefined },
  );
  return data.items;
}

export async function fetchSensorExport(
  sensorId: string,
  params: { from_date?: string; to_date?: string; max_captures?: number } = {},
): Promise<SensorExport> {
  const { data } = await api.get<SensorExport>(
    `/api/v1/sensors/${sensorId}/export`,
    { params },
  );
  return data;
}

/**
 * Pull the CSV through the same axios client as everything else, so the request
 * carries the bearer token and any 401 goes through the usual refresh path. A
 * plain `window.location = url` would send an unauthenticated request and land
 * the user on a 401 page instead of a download.
 */
export async function downloadSensorCsv(
  sensorId: string,
  params: { from_date?: string; to_date?: string; max_captures?: number } = {},
): Promise<void> {
  const response = await api.get(`/api/v1/sensors/${sensorId}/export.csv`, {
    params,
    responseType: "blob",
  });

  const disposition = String(response.headers["content-disposition"] ?? "");
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? `sensor-${sensorId}.csv`;

  const url = URL.createObjectURL(new Blob([response.data], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking immediately can cancel the download in some browsers; a tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

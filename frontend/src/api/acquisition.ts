import api from "./client";
import type { AcquisitionConfig, AcquisitionConfigUpdate } from "@/types/acquisition";

/**
 * Read the acquisition configuration. Public on the backend by default — the
 * edge uploader polls the same URL — but the dashboard still goes through the
 * shared client so an Authorization header is sent when one is available.
 */
export async function getAcquisitionConfig(params?: {
  sensorId?: string;
  deviceId?: string;
}): Promise<AcquisitionConfig> {
  const query: Record<string, string> = {};
  if (params?.sensorId) query.sensor_id = params.sensorId;
  if (params?.deviceId) query.device_id = params.deviceId;
  const res = await api.get("/api/v1/acquisition/config", { params: query });
  return res.data;
}

/** Save acquisition and channel-mapping settings. Admin only. */
export async function saveAcquisitionConfig(
  data: AcquisitionConfigUpdate
): Promise<AcquisitionConfig> {
  const res = await api.put("/api/v1/acquisition/config", data);
  return res.data;
}

import api from "./client";
import type { CaptureHistory, DashboardSummary } from "@/types/dashboard";

export async function getDashboardSummary(plantName?: string): Promise<DashboardSummary> {
  const res = await api.get("/api/v1/dashboard/summary", {
    params: plantName ? { plant_name: plantName } : undefined,
  });
  return res.data;
}

export async function getCaptureHistory(sensorId?: string): Promise<CaptureHistory> {
  const res = await api.get("/api/v1/dashboard/history", {
    params: sensorId ? { sensor_id: sensorId } : undefined,
  });
  return res.data;
}

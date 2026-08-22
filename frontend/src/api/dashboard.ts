import api from "./client";
import type { DashboardSummary } from "@/types/dashboard";

export async function getDashboardSummary(plantName?: string): Promise<DashboardSummary> {
  const res = await api.get("/api/v1/dashboard/summary", {
    params: plantName ? { plant_name: plantName } : undefined,
  });
  return res.data;
}

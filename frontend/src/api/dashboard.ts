import api from "./client";
import type { DashboardSummary } from "@/types/dashboard";

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const res = await api.get("/api/v1/dashboard/summary");
  return res.data;
}

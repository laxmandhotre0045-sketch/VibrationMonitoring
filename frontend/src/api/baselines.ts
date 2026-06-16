import api from "./client";
import type { AllPlotsResponse } from "@/types/measurements";
import type {
  Baseline,
  BaselineCreateFromUpload,
  BaselineListResponse,
} from "@/types/baseline";

export async function listBaselines(sensorId: string): Promise<BaselineListResponse> {
  const res = await api.get("/api/v1/baselines", { params: { sensor_id: sensorId } });
  return res.data;
}

export async function getPrimaryBaseline(sensorId: string): Promise<Baseline | null> {
  try {
    const res = await api.get("/api/v1/baselines/primary", { params: { sensor_id: sensorId } });
    return res.data;
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) return null;
    throw err;
  }
}

export async function createBaselineFromUpload(
  uploadId: string,
  data: BaselineCreateFromUpload
): Promise<Baseline> {
  const res = await api.post(`/api/v1/baselines/from-upload/${uploadId}`, data);
  return res.data;
}

export async function setBaselinePrimary(baselineId: string, isPrimary = true): Promise<Baseline> {
  const res = await api.patch(`/api/v1/baselines/${baselineId}/primary`, { is_primary: isPrimary });
  return res.data;
}

export async function getBaselinePlots(
  baselineId: string,
  channel?: number
): Promise<AllPlotsResponse> {
  const res = await api.get(`/api/v1/baselines/${baselineId}/plots`, {
    params: channel !== undefined ? { channel } : undefined,
  });
  return res.data;
}

import api from "./client";
import type { AllPlotsResponse } from "@/types/measurements";
import type {
  Baseline,
  BaselineCreateFromUpload,
  BaselineFileUpload,
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

/**
 * Upload a CSV/PDF straight into a new baseline.
 *
 * The route is multipart/form-data with every field flat in the body — not
 * JSON — so the payload is assembled here rather than handed to axios as an
 * object. Booleans have to go over as "true"/"false" strings for FastAPI's
 * Form(...) parser to read them back as bools.
 */
export async function uploadBaselineFile(payload: BaselineFileUpload): Promise<Baseline> {
  const form = new FormData();
  form.append("sensor_id", payload.sensorId);
  form.append("channel_count", String(payload.channelCount));
  form.append("name", payload.name);
  if (payload.description) form.append("description", payload.description);
  form.append("set_as_primary", payload.setAsPrimary ? "true" : "false");
  form.append("file", payload.file);

  const res = await api.post("/api/v1/baselines/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
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

import api from "./client";
import type {
  AllPlotsResponse,
  PlotConfig,
  PlotConfigInput,
  PlotSeries,
  SensorDataUpload,
} from "@/types/measurements";

/** Create or update plot config (backend upserts on POST). */
export async function configurePlots(data: PlotConfigInput): Promise<PlotConfig> {
  const res = await api.post("/api/v1/measurements/configure", data);
  return res.data;
}

export async function savePlotConfig(
  sensorId: string,
  data: PlotConfigInput,
  hasExisting?: boolean
): Promise<PlotConfig> {
  if (hasExisting) {
    const { sensor_id: _, ...update } = data;
    return updatePlotConfig(sensorId, update);
  }
  try {
    return await configurePlots(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 409) {
      const { sensor_id: _, ...update } = data;
      return updatePlotConfig(sensorId, update);
    }
    throw err;
  }
}

export async function getPlotConfig(sensorId: string): Promise<PlotConfig> {
  const res = await api.get(`/api/v1/measurements/configure/${sensorId}`);
  return res.data;
}

export async function updatePlotConfig(
  sensorId: string,
  data: Partial<Omit<PlotConfigInput, "sensor_id">>
): Promise<PlotConfig> {
  const res = await api.put(`/api/v1/measurements/configure/${sensorId}`, data);
  return res.data;
}

export async function uploadSensorPdf(
  sensorId: string,
  channelCount: number,
  file: File
): Promise<SensorDataUpload> {
  const form = new FormData();
  form.append("sensor_id", sensorId);
  form.append("channel_count", String(channelCount));
  form.append("file", file);
  const res = await api.post("/api/v1/measurements/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function listUploads(
  sensorId: string,
  filters?: { fromDate?: string; toDate?: string; pageSize?: number }
): Promise<{ items: SensorDataUpload[]; total: number }> {
  const res = await api.get("/api/v1/measurements/uploads", {
    params: {
      sensor_id: sensorId,
      from_date: filters?.fromDate,
      to_date: filters?.toDate,
      page: 1,
      page_size: filters?.pageSize ?? 200,
    },
  });
  const data = res.data;
  if (Array.isArray(data)) {
    return { items: data, total: data.length };
  }
  return {
    items: data.items ?? [],
    total: typeof data.total === "number" ? data.total : (data.items ?? []).length,
  };
}

export async function getAllPlots(uploadId: string, channel?: number): Promise<AllPlotsResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/plots`, {
    params: channel !== undefined ? { channel } : undefined,
  });
  return res.data;
}

export async function getSinglePlot(
  uploadId: string,
  plotType: string,
  channel?: number
): Promise<PlotSeries> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/plots/${plotType}`, {
    params: channel !== undefined ? { channel } : undefined,
  });
  return res.data;
}

export async function getPlotTypes(): Promise<string[]> {
  const res = await api.get("/api/v1/measurements/plot-types");
  return res.data.plot_types;
}

import api from "./client";
import type { AIAnalysis, AIAnswer, AIStatus, AISummary } from "@/types/dashboard";

export async function getAIAnalysis(sensorId?: string): Promise<AIAnalysis> {
  const res = await api.get("/api/v1/ai/analysis", {
    params: sensorId ? { sensor_id: sensorId } : undefined,
  });
  return res.data;
}

export async function getAISummary(sensorId?: string): Promise<AISummary> {
  const res = await api.get("/api/v1/ai/summary", {
    params: sensorId ? { sensor_id: sensorId } : undefined,
  });
  return res.data;
}

export async function getAIStatus(): Promise<AIStatus> {
  const res = await api.get("/api/v1/ai/status");
  return res.data;
}

export async function askAI(question: string, sensorId?: string): Promise<AIAnswer> {
  const res = await api.post("/api/v1/ai/ask", {
    question,
    sensor_id: sensorId ?? null,
  });
  return res.data;
}

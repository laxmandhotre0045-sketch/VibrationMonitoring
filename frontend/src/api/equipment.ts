import api from "./client";
import type { EquipmentFormData, EquipmentOut, PaginatedEquipment, AIReadiness, SensorFormData } from "@/types/equipment";

export async function createEquipment(data: EquipmentFormData): Promise<EquipmentOut> {
  const res = await api.post("/api/v1/equipment/", data);
  return res.data;
}

export async function updateEquipment(id: string, data: Partial<EquipmentFormData>): Promise<EquipmentOut> {
  const res = await api.patch(`/api/v1/equipment/${id}`, data);
  return res.data;
}

export async function getEquipment(id: string): Promise<EquipmentOut> {
  const res = await api.get(`/api/v1/equipment/${id}`);
  return res.data;
}

export async function listEquipment(params?: {
  page?: number;
  page_size?: number;
  plant_name?: string;
  machine_type?: string;
  machine_criticality?: string;
}): Promise<PaginatedEquipment> {
  const res = await api.get("/api/v1/equipment/", { params });
  return res.data;
}

export async function deleteEquipment(id: string): Promise<void> {
  await api.delete(`/api/v1/equipment/${id}`);
}

export async function uploadEquipmentImage(id: string, file: File): Promise<EquipmentOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post(`/api/v1/equipment/${id}/image`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function addSensor(equipmentId: string, data: SensorFormData) {
  const res = await api.post(`/api/v1/equipment/${equipmentId}/sensors`, data);
  return res.data;
}

export async function updateSensor(equipmentId: string, sensorId: string, data: Partial<SensorFormData>) {
  const res = await api.put(`/api/v1/equipment/${equipmentId}/sensors/${sensorId}`, data);
  return res.data;
}

export async function deleteSensor(equipmentId: string, sensorId: string): Promise<void> {
  await api.delete(`/api/v1/equipment/${equipmentId}/sensors/${sensorId}`);
}

export async function getAIReadiness(id: string): Promise<AIReadiness> {
  const res = await api.get(`/api/v1/equipment/${id}/ai-readiness`);
  return res.data;
}

export async function getLookup(name: string): Promise<string[]> {
  const res = await api.get(`/api/v1/lookups/${name}`);
  return res.data.values;
}

export async function getAllLookups(): Promise<Record<string, string[]>> {
  const res = await api.get("/api/v1/lookups/");
  return res.data;
}

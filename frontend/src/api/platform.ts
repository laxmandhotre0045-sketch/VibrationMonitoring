import api from "./client";
import type {
  ApiKey,
  ApiKeyCreated,
  ApiKeyPayload,
  NodePayload,
  Plant,
  PlantArea,
  PlantDetail,
  PlantLine,
  PlantPayload,
  PlatformRole,
  PlatformUser,
  UserCreatePayload,
  UserListFilters,
  UserUpdatePayload,
  Webhook,
  WebhookCreated,
  WebhookDelivery,
  WebhookPayload,
  WebhookTestResult,
  WebhookUpdatePayload,
} from "@/types/platform";

// ── Users ───────────────────────────────────────────────────────────────────

export async function listUsers(filters: UserListFilters = {}): Promise<PlatformUser[]> {
  const params: Record<string, string | boolean> = {};
  if (filters.search) params.search = filters.search;
  if (filters.role) params.role = filters.role;
  if (filters.is_active !== undefined) params.is_active = filters.is_active;

  const res = await api.get("/api/v1/users", { params });
  return res.data;
}

export async function createUser(payload: UserCreatePayload): Promise<PlatformUser> {
  const res = await api.post("/api/v1/users", payload);
  return res.data;
}

export async function updateUser(
  userId: string,
  payload: UserUpdatePayload
): Promise<PlatformUser> {
  const res = await api.patch(`/api/v1/users/${userId}`, payload);
  return res.data;
}

export async function resetUserPassword(
  userId: string,
  newPassword: string
): Promise<PlatformUser> {
  const res = await api.post(`/api/v1/users/${userId}/reset-password`, {
    new_password: newPassword,
    must_change_password: true,
  });
  return res.data;
}

export async function deleteUser(userId: string): Promise<void> {
  await api.delete(`/api/v1/users/${userId}`);
}

export async function listRoles(): Promise<PlatformRole[]> {
  const res = await api.get("/api/v1/roles");
  return res.data;
}

// ── Plant hierarchy ─────────────────────────────────────────────────────────

export async function listPlants(): Promise<Plant[]> {
  const res = await api.get("/api/v1/plants");
  return res.data;
}

export async function getPlant(plantId: string): Promise<PlantDetail> {
  const res = await api.get(`/api/v1/plants/${plantId}`);
  return res.data;
}

export async function createPlant(payload: PlantPayload): Promise<PlantDetail> {
  const res = await api.post("/api/v1/plants", payload);
  return res.data;
}

export async function updatePlant(
  plantId: string,
  payload: Partial<PlantPayload>
): Promise<PlantDetail> {
  const res = await api.patch(`/api/v1/plants/${plantId}`, payload);
  return res.data;
}

export async function deletePlant(plantId: string): Promise<void> {
  await api.delete(`/api/v1/plants/${plantId}`);
}

export async function createArea(plantId: string, payload: NodePayload): Promise<PlantArea> {
  const res = await api.post(`/api/v1/plants/${plantId}/areas`, payload);
  return res.data;
}

export async function updateArea(
  areaId: string,
  payload: Partial<NodePayload>
): Promise<PlantArea> {
  const res = await api.patch(`/api/v1/areas/${areaId}`, payload);
  return res.data;
}

export async function deleteArea(areaId: string): Promise<void> {
  await api.delete(`/api/v1/areas/${areaId}`);
}

export async function createLine(areaId: string, payload: NodePayload): Promise<PlantLine> {
  const res = await api.post(`/api/v1/areas/${areaId}/lines`, payload);
  return res.data;
}

export async function updateLine(
  lineId: string,
  payload: Partial<NodePayload>
): Promise<PlantLine> {
  const res = await api.patch(`/api/v1/lines/${lineId}`, payload);
  return res.data;
}

export async function deleteLine(lineId: string): Promise<void> {
  await api.delete(`/api/v1/lines/${lineId}`);
}

// ── Integrations ────────────────────────────────────────────────────────────

const INTEGRATIONS = "/api/v1/integrations";

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await api.get(`${INTEGRATIONS}/api-keys`);
  return res.data;
}

/** The `key` on the response is the only time the plaintext is ever visible. */
export async function createApiKey(payload: ApiKeyPayload): Promise<ApiKeyCreated> {
  const res = await api.post(`${INTEGRATIONS}/api-keys`, payload);
  return res.data;
}

export async function revokeApiKey(keyId: string): Promise<ApiKey> {
  const res = await api.post(`${INTEGRATIONS}/api-keys/${keyId}/revoke`);
  return res.data;
}

export async function deleteApiKey(keyId: string): Promise<void> {
  await api.delete(`${INTEGRATIONS}/api-keys/${keyId}`);
}

export async function listWebhooks(): Promise<Webhook[]> {
  const res = await api.get(`${INTEGRATIONS}/webhooks`);
  return res.data;
}

/** The `secret` on the response is shown once and never listed again. */
export async function createWebhook(payload: WebhookPayload): Promise<WebhookCreated> {
  const res = await api.post(`${INTEGRATIONS}/webhooks`, payload);
  return res.data;
}

export async function updateWebhook(
  webhookId: string,
  payload: WebhookUpdatePayload
): Promise<Webhook> {
  const res = await api.patch(`${INTEGRATIONS}/webhooks/${webhookId}`, payload);
  return res.data;
}

export async function deleteWebhook(webhookId: string): Promise<void> {
  await api.delete(`${INTEGRATIONS}/webhooks/${webhookId}`);
}

export async function rotateWebhookSecret(webhookId: string): Promise<{ secret: string }> {
  const res = await api.post(`${INTEGRATIONS}/webhooks/${webhookId}/rotate-secret`);
  return res.data;
}

export async function testWebhook(webhookId: string): Promise<WebhookTestResult> {
  const res = await api.post(`${INTEGRATIONS}/webhooks/${webhookId}/test`);
  return res.data;
}

export async function listWebhookDeliveries(
  webhookId: string,
  limit = 20
): Promise<WebhookDelivery[]> {
  const res = await api.get(`${INTEGRATIONS}/webhooks/${webhookId}/deliveries`, {
    params: { limit },
  });
  return res.data;
}

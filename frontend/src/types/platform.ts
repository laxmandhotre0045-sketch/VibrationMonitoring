/**
 * Platform settings — users, plant hierarchy and integrations.
 *
 * Mirrors backend app/schemas/{user,plant,integration}.py. Two fields are
 * write-once and only ever present on a create response: `ApiKeyCreated.key`
 * and `WebhookCreated.secret`. Neither is retrievable afterwards, which is why
 * they live on separate types rather than being optional on the list shape.
 */

// ── Users ───────────────────────────────────────────────────────────────────

export interface PlatformUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  roles: string[];
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface PlatformRole {
  name: string;
  description: string | null;
  user_count: number;
}

export interface UserCreatePayload {
  email: string;
  full_name: string;
  password: string;
  role: string;
  is_active?: boolean;
  must_change_password?: boolean;
}

export interface UserUpdatePayload {
  full_name?: string;
  role?: string;
  is_active?: boolean;
}

export interface UserListFilters {
  search?: string;
  role?: string;
  is_active?: boolean;
}

// ── Plant hierarchy ─────────────────────────────────────────────────────────

export interface PlantLine {
  id: string;
  area_id: string;
  name: string;
  is_active: boolean;
  equipment_count: number;
}

export interface PlantArea {
  id: string;
  plant_id: string;
  name: string;
  is_active: boolean;
  equipment_count: number;
  lines: PlantLine[];
}

export interface Plant {
  id: string;
  name: string;
  code: string | null;
  location: string | null;
  is_active: boolean;
  area_count: number;
  equipment_count: number;
  created_at: string;
}

export interface PlantDetail extends Plant {
  areas: PlantArea[];
}

export interface PlantPayload {
  name: string;
  code?: string | null;
  location?: string | null;
  is_active?: boolean;
}

export interface NodePayload {
  name: string;
  is_active?: boolean;
}

// ── Integrations ────────────────────────────────────────────────────────────

export const WEBHOOK_SEVERITIES = ["warning", "critical"] as const;
export type WebhookSeverity = (typeof WEBHOOK_SEVERITIES)[number];

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}

/** Only returned by the create call — `key` is never retrievable again. */
export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export interface ApiKeyPayload {
  name: string;
  expires_at?: string | null;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  min_severity: string;
  is_active: boolean;
  headers: Record<string, string>;
  last_status_code: number | null;
  last_triggered_at: string | null;
  consecutive_failures: number;
  created_at: string | null;
}

/** Only returned by create — the signing secret is never listed again. */
export interface WebhookCreated extends Webhook {
  secret: string;
}

export interface WebhookPayload {
  name: string;
  url: string;
  min_severity: WebhookSeverity;
  is_active?: boolean;
  headers?: Record<string, string>;
}

export interface WebhookUpdatePayload {
  name?: string;
  url?: string;
  min_severity?: WebhookSeverity;
  is_active?: boolean;
  headers?: Record<string, string>;
}

export interface WebhookDelivery {
  id: string;
  event: string;
  status_code: number | null;
  error: string | null;
  duration_ms: number | null;
  succeeded: boolean;
  created_at: string | null;
}

export interface WebhookTestResult {
  delivered: boolean;
  status_code: number | null;
  error: string | null;
  duration_ms: number | null;
}

export type PlatformSectionId = "users" | "plants" | "integrations";

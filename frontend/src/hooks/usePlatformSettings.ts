import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as platformApi from "@/api/platform";
import { apiErrorMessage } from "@/lib/api-error";
import { useToast } from "@/components/ui/Toast";
import type { UserListFilters } from "@/types/platform";

export const platformKeys = {
  users: (filters: UserListFilters) => ["platform", "users", filters] as const,
  roles: ["platform", "roles"] as const,
  plants: ["platform", "plants"] as const,
  plant: (id: string) => ["platform", "plant", id] as const,
  apiKeys: ["platform", "api-keys"] as const,
  webhooks: ["platform", "webhooks"] as const,
  deliveries: (id: string) => ["platform", "webhook-deliveries", id] as const,
};

/**
 * Every mutation here goes through the same success/failure handling: a toast,
 * then an invalidation of whatever list the change affects. Wrapping it once
 * keeps the section components free of repeated boilerplate and guarantees a
 * failed call always surfaces the server's own message rather than a generic one.
 */
function usePlatformMutation<TArgs, TResult>(options: {
  mutationFn: (args: TArgs) => Promise<TResult>;
  invalidate: readonly (readonly unknown[])[];
  successMessage: string | ((result: TResult) => string);
  errorFallback: string;
  onSuccess?: (result: TResult, args: TArgs) => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: options.mutationFn,
    onSuccess: (result, args) => {
      options.invalidate.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
      const message =
        typeof options.successMessage === "function"
          ? options.successMessage(result)
          : options.successMessage;
      showToast(message, "success");
      options.onSuccess?.(result, args);
    },
    onError: (error) => {
      showToast(apiErrorMessage(error, options.errorFallback), "error");
    },
  });
}

// ── Users ───────────────────────────────────────────────────────────────────

export function useUsers(filters: UserListFilters) {
  return useQuery({
    queryKey: platformKeys.users(filters),
    queryFn: () => platformApi.listUsers(filters),
    retry: 1,
  });
}

export function useRoles() {
  return useQuery({
    queryKey: platformKeys.roles,
    queryFn: platformApi.listRoles,
    retry: 1,
    staleTime: 5 * 60_000,
  });
}

const USER_LISTS = [["platform", "users"], ["platform", "roles"]];

export function useCreateUser(onCreated?: () => void) {
  return usePlatformMutation({
    mutationFn: platformApi.createUser,
    invalidate: USER_LISTS,
    successMessage: (user) => `User ${user.email} created`,
    errorFallback: "Failed to create user",
    onSuccess: () => onCreated?.(),
  });
}

export function useUpdateUser(onUpdated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { userId: string; payload: Parameters<typeof platformApi.updateUser>[1] }) =>
      platformApi.updateUser(args.userId, args.payload),
    invalidate: USER_LISTS,
    successMessage: "User updated",
    errorFallback: "Failed to update user",
    onSuccess: () => onUpdated?.(),
  });
}

export function useResetPassword(onReset?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { userId: string; newPassword: string }) =>
      platformApi.resetUserPassword(args.userId, args.newPassword),
    invalidate: USER_LISTS,
    successMessage: "Password reset — the user must change it at next sign-in",
    errorFallback: "Failed to reset password",
    onSuccess: () => onReset?.(),
  });
}

export function useDeleteUser() {
  return usePlatformMutation({
    mutationFn: platformApi.deleteUser,
    invalidate: USER_LISTS,
    successMessage: "User deleted",
    errorFallback: "Failed to delete user",
  });
}

// ── Plant hierarchy ─────────────────────────────────────────────────────────

export function usePlants() {
  return useQuery({
    queryKey: platformKeys.plants,
    queryFn: platformApi.listPlants,
    retry: 1,
  });
}

export function usePlantDetail(plantId: string | null) {
  return useQuery({
    queryKey: platformKeys.plant(plantId ?? ""),
    queryFn: () => platformApi.getPlant(plantId!),
    enabled: Boolean(plantId),
    retry: 1,
  });
}

/**
 * Area and line changes alter the counts shown on the plant list as well as the
 * expanded tree, so both are invalidated on every hierarchy mutation.
 */
const HIERARCHY = [["platform", "plants"], ["platform", "plant"]];

export function useCreatePlant(onCreated?: () => void) {
  return usePlatformMutation({
    mutationFn: platformApi.createPlant,
    invalidate: HIERARCHY,
    successMessage: (plant) => `Plant "${plant.name}" created`,
    errorFallback: "Failed to create plant",
    onSuccess: () => onCreated?.(),
  });
}

export function useUpdatePlant(onUpdated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { plantId: string; payload: Parameters<typeof platformApi.updatePlant>[1] }) =>
      platformApi.updatePlant(args.plantId, args.payload),
    // A plant rename cascades to every equipment record's denormalised
    // plant_name, so equipment lists and lookups have to be refetched too.
    invalidate: [...HIERARCHY, ["equipment"], ["lookups"], ["dashboard-summary"]],
    successMessage: "Plant updated",
    errorFallback: "Failed to update plant",
    onSuccess: () => onUpdated?.(),
  });
}

export function useDeletePlant() {
  return usePlatformMutation({
    mutationFn: platformApi.deletePlant,
    invalidate: HIERARCHY,
    successMessage: "Plant deleted",
    errorFallback: "Failed to delete plant",
  });
}

export function useCreateArea(onCreated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { plantId: string; name: string }) =>
      platformApi.createArea(args.plantId, { name: args.name }),
    invalidate: HIERARCHY,
    successMessage: "Area added",
    errorFallback: "Failed to add area",
    onSuccess: () => onCreated?.(),
  });
}

export function useUpdateArea(onUpdated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { areaId: string; payload: Parameters<typeof platformApi.updateArea>[1] }) =>
      platformApi.updateArea(args.areaId, args.payload),
    invalidate: [...HIERARCHY, ["equipment"], ["lookups"]],
    successMessage: "Area updated",
    errorFallback: "Failed to update area",
    onSuccess: () => onUpdated?.(),
  });
}

export function useDeleteArea() {
  return usePlatformMutation({
    mutationFn: platformApi.deleteArea,
    invalidate: HIERARCHY,
    successMessage: "Area deleted",
    errorFallback: "Failed to delete area",
  });
}

export function useCreateLine(onCreated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { areaId: string; name: string }) =>
      platformApi.createLine(args.areaId, { name: args.name }),
    invalidate: HIERARCHY,
    successMessage: "Line added",
    errorFallback: "Failed to add line",
    onSuccess: () => onCreated?.(),
  });
}

export function useUpdateLine(onUpdated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: { lineId: string; payload: Parameters<typeof platformApi.updateLine>[1] }) =>
      platformApi.updateLine(args.lineId, args.payload),
    invalidate: [...HIERARCHY, ["equipment"], ["lookups"]],
    successMessage: "Line updated",
    errorFallback: "Failed to update line",
    onSuccess: () => onUpdated?.(),
  });
}

export function useDeleteLine() {
  return usePlatformMutation({
    mutationFn: platformApi.deleteLine,
    invalidate: HIERARCHY,
    successMessage: "Line deleted",
    errorFallback: "Failed to delete line",
  });
}

// ── Integrations ────────────────────────────────────────────────────────────

export function useApiKeys() {
  return useQuery({
    queryKey: platformKeys.apiKeys,
    queryFn: platformApi.listApiKeys,
    retry: 1,
  });
}

export function useCreateApiKey(onCreated?: (key: string) => void) {
  return usePlatformMutation({
    mutationFn: platformApi.createApiKey,
    invalidate: [platformKeys.apiKeys],
    successMessage: "API key created",
    errorFallback: "Failed to create API key",
    onSuccess: (result) => onCreated?.(result.key),
  });
}

export function useRevokeApiKey() {
  return usePlatformMutation({
    mutationFn: platformApi.revokeApiKey,
    invalidate: [platformKeys.apiKeys],
    successMessage: "API key revoked",
    errorFallback: "Failed to revoke API key",
  });
}

export function useDeleteApiKey() {
  return usePlatformMutation({
    mutationFn: platformApi.deleteApiKey,
    invalidate: [platformKeys.apiKeys],
    successMessage: "API key deleted",
    errorFallback: "Failed to delete API key",
  });
}

export function useWebhooks() {
  return useQuery({
    queryKey: platformKeys.webhooks,
    queryFn: platformApi.listWebhooks,
    retry: 1,
  });
}

export function useWebhookDeliveries(webhookId: string | null) {
  return useQuery({
    queryKey: platformKeys.deliveries(webhookId ?? ""),
    queryFn: () => platformApi.listWebhookDeliveries(webhookId!),
    enabled: Boolean(webhookId),
    retry: 1,
  });
}

export function useCreateWebhook(onCreated?: (secret: string) => void) {
  return usePlatformMutation({
    mutationFn: platformApi.createWebhook,
    invalidate: [platformKeys.webhooks],
    successMessage: "Webhook created",
    errorFallback: "Failed to create webhook",
    onSuccess: (result) => onCreated?.(result.secret),
  });
}

export function useUpdateWebhook(onUpdated?: () => void) {
  return usePlatformMutation({
    mutationFn: (args: {
      webhookId: string;
      payload: Parameters<typeof platformApi.updateWebhook>[1];
    }) => platformApi.updateWebhook(args.webhookId, args.payload),
    invalidate: [platformKeys.webhooks],
    successMessage: "Webhook updated",
    errorFallback: "Failed to update webhook",
    onSuccess: () => onUpdated?.(),
  });
}

export function useDeleteWebhook() {
  return usePlatformMutation({
    mutationFn: platformApi.deleteWebhook,
    invalidate: [platformKeys.webhooks],
    successMessage: "Webhook deleted",
    errorFallback: "Failed to delete webhook",
  });
}

export function useRotateWebhookSecret(onRotated?: (secret: string) => void) {
  return usePlatformMutation({
    mutationFn: platformApi.rotateWebhookSecret,
    invalidate: [platformKeys.webhooks],
    successMessage: "Signing secret rotated",
    errorFallback: "Failed to rotate secret",
    onSuccess: (result) => onRotated?.(result.secret),
  });
}

/**
 * A test that reaches the endpoint and comes back non-2xx is still a successful
 * API call, so the toast has to reflect the delivery result, not the HTTP call.
 */
export function useTestWebhook() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: platformApi.testWebhook,
    onSuccess: (result, webhookId) => {
      queryClient.invalidateQueries({ queryKey: platformKeys.webhooks });
      queryClient.invalidateQueries({ queryKey: platformKeys.deliveries(webhookId) });
      if (result.delivered) {
        showToast(`Test delivered — ${result.status_code} in ${result.duration_ms ?? 0}ms`, "success");
      } else {
        showToast(
          result.error ?? `Endpoint responded ${result.status_code ?? "with no status"}`,
          "error"
        );
      }
    },
    onError: (error) => {
      showToast(apiErrorMessage(error, "Failed to send test"), "error");
    },
  });
}

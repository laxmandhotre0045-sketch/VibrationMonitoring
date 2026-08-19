import React, { useState } from "react";
import {
  Ban,
  History,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Webhook as WebhookIcon,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField, SelectInput, TextInput } from "@/components/ui/FormField";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ConfirmDialog, PlatformDialog } from "./PlatformDialog";
import {
  EmptyRow,
  ErrorNote,
  IconAction,
  LoadingRow,
  SecretReveal,
  StatusPill,
  formatDateTime,
  platformTable,
  platformTableWrapper,
  platformTd,
  platformTh,
} from "./platform-ui";
import {
  useApiKeys,
  useCreateApiKey,
  useCreateWebhook,
  useDeleteApiKey,
  useDeleteWebhook,
  useRevokeApiKey,
  useRotateWebhookSecret,
  useTestWebhook,
  useUpdateWebhook,
  useWebhookDeliveries,
  useWebhooks,
} from "@/hooks/usePlatformSettings";
import { apiErrorMessage } from "@/lib/api-error";
import { WEBHOOK_SEVERITIES, type ApiKey, type Webhook, type WebhookSeverity } from "@/types/platform";

export function IntegrationsSection() {
  return (
    <div className="space-y-g4">
      <ApiKeysCard />
      <WebhooksCard />
    </div>
  );
}

// ── API keys ────────────────────────────────────────────────────────────────

function ApiKeysCard() {
  const { data: keys, isLoading, error } = useApiKeys();
  const [createOpen, setCreateOpen] = useState(false);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  const [deleting, setDeleting] = useState<ApiKey | null>(null);

  const revokeKey = useRevokeApiKey();
  const deleteKey = useDeleteApiKey();

  return (
    <>
      <SettingsSectionCard
        title="Device API keys"
        description="Keys let a gateway or edge device push measurements without a user session. Send one as the X-API-Key header."
        icon={<KeyRound size={18} />}
      >
        <div className="flex items-center justify-between gap-g2 mb-g3">
          <p className="text-sm text-muted-foreground">
            {keys?.filter((k) => k.is_active).length ?? 0} active of {keys?.length ?? 0}
          </p>
          <Button size="sm" icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            Create key
          </Button>
        </div>

        {error && <ErrorNote message={apiErrorMessage(error, "Failed to load API keys")} />}

        <div className={platformTableWrapper}>
          <table className={platformTable}>
            <thead>
              <tr>
                <th className={platformTh}>Name</th>
                <th className={platformTh}>Key</th>
                <th className={platformTh}>Status</th>
                <th className={platformTh}>Last used</th>
                <th className={platformTh}>Expires</th>
                <th className={platformTh}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <LoadingRow colSpan={6} />}
              {!isLoading && !keys?.length && (
                <EmptyRow colSpan={6} message="No API keys yet." />
              )}
              {keys?.map((key) => (
                <tr key={key.id} className="hover:bg-warm/60 transition-colors">
                  <td className={`${platformTd} font-semibold text-foreground`}>{key.name}</td>
                  <td className={`${platformTd} font-mono text-xs text-muted-foreground`}>
                    {key.key_prefix}…
                  </td>
                  <td className={platformTd}>
                    {key.revoked_at ? (
                      <StatusPill tone="danger">Revoked</StatusPill>
                    ) : key.is_active ? (
                      <StatusPill tone="healthy">Active</StatusPill>
                    ) : (
                      <StatusPill tone="muted">Expired</StatusPill>
                    )}
                  </td>
                  <td className={`${platformTd} text-muted-foreground whitespace-nowrap`}>
                    {formatDateTime(key.last_used_at)}
                  </td>
                  <td className={`${platformTd} text-muted-foreground whitespace-nowrap`}>
                    {key.expires_at ? formatDateTime(key.expires_at) : "Never"}
                  </td>
                  <td className={platformTd}>
                    <div className="flex items-center gap-1">
                      <IconAction
                        label="Revoke key"
                        disabled={Boolean(key.revoked_at)}
                        onClick={() => setRevoking(key)}
                      >
                        <Ban size={15} />
                      </IconAction>
                      <IconAction
                        label="Delete key"
                        tone="danger"
                        onClick={() => setDeleting(key)}
                      >
                        <Trash2 size={15} />
                      </IconAction>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SettingsSectionCard>

      <CreateApiKeyDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      <ConfirmDialog
        open={Boolean(revoking)}
        title="Revoke API key"
        confirmLabel="Revoke key"
        busy={revokeKey.isPending}
        message={
          <>
            Any device still using <strong>{revoking?.name}</strong> will start getting 401s
            immediately. The key stays listed so you can see when it was last used, but it can
            never be re-enabled — issue a new one instead.
          </>
        }
        onClose={() => setRevoking(null)}
        onConfirm={() => {
          if (!revoking) return;
          revokeKey.mutate(revoking.id, { onSuccess: () => setRevoking(null) });
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete API key"
        confirmLabel="Delete key"
        busy={deleteKey.isPending}
        message={
          <>
            <strong>{deleting?.name}</strong> will be removed along with its usage history. Any
            device still using it will start getting 401s.
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          deleteKey.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
      />
    </>
  );
}

function CreateApiKeyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [issuedKey, setIssuedKey] = useState<string | null>(null);

  const createKey = useCreateApiKey((key) => setIssuedKey(key));

  function close() {
    setName("");
    setExpiresAt("");
    setIssuedKey(null);
    onClose();
  }

  if (issuedKey) {
    return (
      <PlatformDialog
        open={open}
        title="API key created"
        onClose={close}
        footer={
          <Button size="sm" onClick={close}>
            Done
          </Button>
        }
      >
        <SecretReveal
          label="API key"
          secret={issuedKey}
          warning="Only a hash of this key is stored, so this is the one and only time it can be shown. Copy it into the device configuration now — if you lose it, revoke this key and issue another."
        />
      </PlatformDialog>
    );
  }

  return (
    <PlatformDialog
      open={open}
      title="Create API key"
      description="Name it after the device or integration that will hold it, so a revocation later is unambiguous."
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!name.trim() || createKey.isPending}
            onClick={() =>
              createKey.mutate({
                name: name.trim(),
                // datetime-local has no zone; the backend stores naive UTC, so
                // sending the literal value keeps it consistent with the rest.
                expires_at: expiresAt ? `${expiresAt}:00` : null,
              })
            }
          >
            {createKey.isPending ? "Creating…" : "Create key"}
          </Button>
        </>
      }
    >
      <FormField label="Name" required compact>
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Gateway — Compressor House"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField label="Expires" compact hint="Leave empty for a key that never expires.">
        <TextInput
          type="datetime-local"
          value={expiresAt}
          onChange={(e) => setExpiresAt(e.target.value)}
          className="py-2.5 text-sm"
        />
      </FormField>
    </PlatformDialog>
  );
}

// ── Webhooks ────────────────────────────────────────────────────────────────

function WebhooksCard() {
  const { data: webhooks, isLoading, error } = useWebhooks();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Webhook | null>(null);
  const [deleting, setDeleting] = useState<Webhook | null>(null);
  const [rotating, setRotating] = useState<Webhook | null>(null);
  const [viewingLog, setViewingLog] = useState<Webhook | null>(null);

  const deleteWebhook = useDeleteWebhook();
  const testWebhook = useTestWebhook();

  return (
    <>
      <SettingsSectionCard
        title="Alert webhooks"
        description="Every measurement that breaches a threshold is POSTed to these endpoints, signed with HMAC-SHA256 so the receiver can verify it came from here."
        icon={<WebhookIcon size={18} />}
      >
        <div className="flex items-center justify-between gap-g2 mb-g3">
          <p className="text-sm text-muted-foreground">
            {webhooks?.filter((w) => w.is_active).length ?? 0} active of {webhooks?.length ?? 0}
          </p>
          <Button size="sm" icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            Add webhook
          </Button>
        </div>

        {error && <ErrorNote message={apiErrorMessage(error, "Failed to load webhooks")} />}

        <div className={platformTableWrapper}>
          <table className={platformTable}>
            <thead>
              <tr>
                <th className={platformTh}>Name</th>
                <th className={platformTh}>Endpoint</th>
                <th className={platformTh}>Fires on</th>
                <th className={platformTh}>Status</th>
                <th className={platformTh}>Last delivery</th>
                <th className={platformTh}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <LoadingRow colSpan={6} />}
              {!isLoading && !webhooks?.length && (
                <EmptyRow colSpan={6} message="No webhooks configured." />
              )}
              {webhooks?.map((hook) => (
                <tr key={hook.id} className="hover:bg-warm/60 transition-colors">
                  <td className={`${platformTd} font-semibold text-foreground`}>{hook.name}</td>
                  <td className={`${platformTd} max-w-[260px]`}>
                    <span className="block truncate font-mono text-xs text-muted-foreground">
                      {hook.url}
                    </span>
                  </td>
                  <td className={platformTd}>
                    <StatusPill tone={hook.min_severity === "critical" ? "danger" : "warning"}>
                      {hook.min_severity === "critical" ? "Critical only" : "Warning +"}
                    </StatusPill>
                  </td>
                  <td className={platformTd}>
                    <div className="flex flex-wrap gap-1.5">
                      <StatusPill tone={hook.is_active ? "healthy" : "muted"}>
                        {hook.is_active ? "Active" : "Paused"}
                      </StatusPill>
                      {hook.consecutive_failures > 0 && (
                        <StatusPill tone="danger">
                          {hook.consecutive_failures} failed in a row
                        </StatusPill>
                      )}
                    </div>
                  </td>
                  <td className={`${platformTd} text-muted-foreground whitespace-nowrap`}>
                    {hook.last_triggered_at ? (
                      <>
                        {formatDateTime(hook.last_triggered_at)}
                        {hook.last_status_code != null && (
                          <span className="ml-1.5 font-mono text-xs">
                            ({hook.last_status_code})
                          </span>
                        )}
                      </>
                    ) : (
                      "Never"
                    )}
                  </td>
                  <td className={platformTd}>
                    <div className="flex items-center gap-1">
                      <IconAction
                        label="Send test delivery"
                        disabled={testWebhook.isPending}
                        onClick={() => testWebhook.mutate(hook.id)}
                      >
                        <Send size={15} />
                      </IconAction>
                      <IconAction label="Delivery log" onClick={() => setViewingLog(hook)}>
                        <History size={15} />
                      </IconAction>
                      <IconAction label="Rotate signing secret" onClick={() => setRotating(hook)}>
                        <RefreshCw size={15} />
                      </IconAction>
                      <IconAction label="Edit webhook" onClick={() => setEditing(hook)}>
                        <Pencil size={15} />
                      </IconAction>
                      <IconAction
                        label="Delete webhook"
                        tone="danger"
                        onClick={() => setDeleting(hook)}
                      >
                        <Trash2 size={15} />
                      </IconAction>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SettingsSectionCard>

      <WebhookFormDialog open={createOpen} webhook={null} onClose={() => setCreateOpen(false)} />
      <WebhookFormDialog
        open={Boolean(editing)}
        webhook={editing}
        onClose={() => setEditing(null)}
      />
      <RotateSecretDialog webhook={rotating} onClose={() => setRotating(null)} />
      <DeliveryLogDialog webhook={viewingLog} onClose={() => setViewingLog(null)} />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete webhook"
        confirmLabel="Delete webhook"
        busy={deleteWebhook.isPending}
        message={
          <>
            <strong>{deleting?.name}</strong> will stop receiving alerts and its delivery history
            will be removed. To silence it temporarily, edit it and untick "Active" instead.
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          deleteWebhook.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
      />
    </>
  );
}

const SEVERITY_LABELS: Record<WebhookSeverity, string> = {
  warning: "Warning and above",
  critical: "Critical only",
};

function WebhookFormDialog({
  open,
  webhook,
  onClose,
}: {
  open: boolean;
  webhook: Webhook | null;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [severity, setSeverity] = useState<WebhookSeverity>("warning");
  const [isActive, setIsActive] = useState(true);
  const [issuedSecret, setIssuedSecret] = useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setName(webhook?.name ?? "");
    setUrl(webhook?.url ?? "");
    setSeverity((webhook?.min_severity as WebhookSeverity) ?? "warning");
    setIsActive(webhook?.is_active ?? true);
    setIssuedSecret(null);
  }, [open, webhook]);

  function close() {
    setIssuedSecret(null);
    onClose();
  }

  const createWebhook = useCreateWebhook((secret) => setIssuedSecret(secret));
  const updateWebhook = useUpdateWebhook(close);
  const pending = createWebhook.isPending || updateWebhook.isPending;

  const urlLooksValid = /^https?:\/\/.+/i.test(url.trim());

  if (issuedSecret) {
    return (
      <PlatformDialog
        open={open}
        title="Webhook created"
        onClose={close}
        footer={
          <Button size="sm" onClick={close}>
            Done
          </Button>
        }
      >
        <SecretReveal
          label="Signing secret"
          secret={issuedSecret}
          warning="Your endpoint uses this to verify the X-SensoVibe-Signature header — an HMAC-SHA256 over the timestamp and body. It is stored only here, so copy it now; if it is lost, rotate to get a new one."
        />
      </PlatformDialog>
    );
  }

  return (
    <PlatformDialog
      open={open}
      title={webhook ? "Edit webhook" : "Add webhook"}
      description={
        webhook
          ? undefined
          : "A signing secret is generated on creation and shown once."
      }
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!name.trim() || !urlLooksValid || pending}
            onClick={() => {
              const payload = {
                name: name.trim(),
                url: url.trim(),
                min_severity: severity,
                is_active: isActive,
              };
              if (webhook) {
                updateWebhook.mutate({ webhookId: webhook.id, payload });
              } else {
                createWebhook.mutate({ ...payload, headers: {} });
              }
            }}
          >
            {pending ? "Saving…" : webhook ? "Save changes" : "Create webhook"}
          </Button>
        </>
      }
    >
      <FormField label="Name" required compact>
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Maintenance Slack channel"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField
        label="Endpoint URL"
        required
        compact
        error={url.trim() && !urlLooksValid ? "Must start with http:// or https://" : undefined}
      >
        <TextInput
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://hooks.example.com/sensovibe"
          className="py-2.5 text-sm font-mono"
        />
      </FormField>
      <FormField
        label="Fires on"
        compact
        hint="Critical only skips warnings entirely — useful for a paging endpoint."
      >
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as WebhookSeverity)}
          className="w-full cursor-pointer appearance-none rounded-lg border border-border bg-white px-4 py-2.5 text-sm text-foreground focus:border-signal-light focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]"
        >
          {WEBHOOK_SEVERITIES.map((value) => (
            <option key={value} value={value}>
              {SEVERITY_LABELS[value]}
            </option>
          ))}
        </select>
      </FormField>
      <label className="flex items-center gap-2.5 text-sm text-foreground cursor-pointer">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-[#FF6B00]"
        />
        <span>
          Active
          <span className="block text-xs text-muted-foreground">
            Re-enabling a webhook also clears its consecutive failure count.
          </span>
        </span>
      </label>
    </PlatformDialog>
  );
}

function RotateSecretDialog({
  webhook,
  onClose,
}: {
  webhook: Webhook | null;
  onClose: () => void;
}) {
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const rotate = useRotateWebhookSecret((secret) => setNewSecret(secret));

  React.useEffect(() => {
    if (webhook) setNewSecret(null);
  }, [webhook]);

  function close() {
    setNewSecret(null);
    onClose();
  }

  if (newSecret) {
    return (
      <PlatformDialog
        open={Boolean(webhook)}
        title="Secret rotated"
        onClose={close}
        footer={
          <Button size="sm" onClick={close}>
            Done
          </Button>
        }
      >
        <SecretReveal
          label="New signing secret"
          secret={newSecret}
          warning="Deliveries are already being signed with this. Update your endpoint now — until you do, signature checks there will fail."
        />
      </PlatformDialog>
    );
  }

  return (
    <ConfirmDialog
      open={Boolean(webhook)}
      title="Rotate signing secret"
      confirmLabel="Rotate secret"
      destructive={false}
      busy={rotate.isPending}
      message={
        <>
          The next delivery to <strong>{webhook?.name}</strong> will be signed with a new secret.
          Signature verification at your endpoint will fail until you update it there, so have the
          receiver ready to take the new value.
        </>
      }
      onClose={close}
      onConfirm={() => webhook && rotate.mutate(webhook.id)}
    />
  );
}

function DeliveryLogDialog({
  webhook,
  onClose,
}: {
  webhook: Webhook | null;
  onClose: () => void;
}) {
  const { data: deliveries, isLoading } = useWebhookDeliveries(webhook?.id ?? null);

  return (
    <PlatformDialog
      open={Boolean(webhook)}
      title="Delivery log"
      description={webhook ? `Last 20 attempts to ${webhook.name}` : undefined}
      widthClassName="max-w-2xl"
      onClose={onClose}
      footer={
        <Button variant="secondary" size="sm" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className={platformTableWrapper}>
        <table className={`${platformTable} min-w-[520px]`}>
          <thead>
            <tr>
              <th className={platformTh}>When</th>
              <th className={platformTh}>Event</th>
              <th className={platformTh}>Result</th>
              <th className={platformTh}>Took</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <LoadingRow colSpan={4} />}
            {!isLoading && !deliveries?.length && (
              <EmptyRow colSpan={4} message="Nothing delivered yet." />
            )}
            {deliveries?.map((delivery) => (
              <tr key={delivery.id}>
                <td className={`${platformTd} whitespace-nowrap text-muted-foreground`}>
                  {formatDateTime(delivery.created_at)}
                </td>
                <td className={`${platformTd} font-mono text-xs`}>{delivery.event}</td>
                <td className={platformTd}>
                  {delivery.succeeded ? (
                    <StatusPill tone="healthy">{delivery.status_code}</StatusPill>
                  ) : (
                    <div className="space-y-1">
                      <StatusPill tone="danger">
                        {delivery.status_code ?? "No response"}
                      </StatusPill>
                      {delivery.error && (
                        <p className="max-w-[240px] break-words text-xs text-muted-foreground">
                          {delivery.error}
                        </p>
                      )}
                    </div>
                  )}
                </td>
                <td className={`${platformTd} whitespace-nowrap text-muted-foreground`}>
                  {delivery.duration_ms != null ? `${delivery.duration_ms} ms` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PlatformDialog>
  );
}

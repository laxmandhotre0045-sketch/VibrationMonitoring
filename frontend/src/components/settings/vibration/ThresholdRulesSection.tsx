import React, { useCallback, useMemo, useState } from "react";
import { AlertTriangle, Gauge, Loader2, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { useThresholdRules } from "@/hooks/useThresholdRules";
import { formatApiChannelLabel, displayChannelToApi } from "@/lib/threshold-rule-adapters";
import { VIBRATION_CHANNEL_COUNT } from "@/types/vibration-settings";
import type {
  ThresholdLimitField,
  ThresholdRule,
  ThresholdRuleBulkItem,
  ThresholdScopeSensor,
} from "@/types/thresholds";
import { cn } from "@/lib/utils";

const ADMIN_ROLES = ["admin", "super_admin"] as const;

/**
 * Limits in the order a reading crosses them, low side first. The evaluator
 * calls them normal/warning; the health screens call them caution/warning.
 * These headers follow the health screens so one reading has one vocabulary.
 */
const LIMIT_FIELDS: ThresholdLimitField[] = [
  "warning_min",
  "normal_min",
  "normal_max",
  "warning_max",
];

const LIMIT_HEADERS: Record<ThresholdLimitField, string> = {
  warning_min: "Warning Min",
  normal_min: "Caution Min",
  normal_max: "Caution Max",
  warning_max: "Warning Max",
};

type LimitDraft = Partial<Record<ThresholdLimitField, string>> & { is_active?: boolean };

function limitToInput(value: number | null): string {
  return value === null || value === undefined ? "" : String(value);
}

function inputToLimit(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function effectiveLimit(
  rule: ThresholdRule,
  field: ThresholdLimitField,
  draft: LimitDraft | undefined
): number | null {
  const pending = draft?.[field];
  return pending === undefined ? rule[field] : inputToLimit(pending);
}

/** Mirrors the ordering the API enforces, so a bad row is caught before saving. */
function validateRow(rule: ThresholdRule, draft: LimitDraft | undefined): string | null {
  const normalMax = effectiveLimit(rule, "normal_max", draft);
  const warningMax = effectiveLimit(rule, "warning_max", draft);
  const normalMin = effectiveLimit(rule, "normal_min", draft);
  const warningMin = effectiveLimit(rule, "warning_min", draft);

  if (normalMax !== null && warningMax !== null && warningMax <= normalMax) {
    return "Warning max must be greater than caution max.";
  }
  if (normalMin !== null && warningMin !== null && warningMin >= normalMin) {
    return "Warning min must be less than caution min.";
  }
  if (normalMin !== null && normalMax !== null && normalMin >= normalMax) {
    return "Caution min must be less than caution max.";
  }
  return null;
}

/**
 * The one row every other row falls back to: narrowed in no way at all.
 *
 * Checked on every scope column rather than on `channel` alone. A rule written
 * for one sensor also has a null channel, so testing the channel by itself
 * would file it as the feature's global rule and hide the real one.
 */
function isGlobalRule(rule: ThresholdRule): boolean {
  return (
    rule.channel === null &&
    rule.sensor_id === null &&
    rule.equipment_id === null &&
    (rule.machine_type === null || rule.machine_type.trim() === "")
  );
}

/** Narrowest scope first, so a feature's overrides read in precedence order. */
function scopeRank(rule: ThresholdRule): number {
  if (rule.sensor_id) return 0;
  if (rule.equipment_id) return 1;
  if (rule.machine_type && rule.machine_type.trim() !== "") return 2;
  if (rule.channel !== null) return 3;
  return 4;
}

/** How a rule's scope reads in the table, narrowest part first. */
function scopeText(
  rule: ThresholdRule,
  sensorsById: Map<string, ThresholdScopeSensor>,
  machineNameById: Map<string, string>
): string {
  const parts: string[] = [];
  if (rule.sensor_id) {
    parts.push(sensorsById.get(rule.sensor_id)?.label ?? "Sensor");
  } else if (rule.equipment_id) {
    parts.push(machineNameById.get(rule.equipment_id) ?? "Machine");
  } else if (rule.machine_type && rule.machine_type.trim() !== "") {
    parts.push(`Type: ${rule.machine_type}`);
  }

  parts.push(
    rule.channel !== null ? formatApiChannelLabel(rule.channel) : "All channels"
  );
  return parts.join(" · ");
}

function draftToPatch(rule: ThresholdRule, draft: LimitDraft): ThresholdRuleBulkItem {
  const patch: ThresholdRuleBulkItem = { id: rule.id };
  for (const field of LIMIT_FIELDS) {
    const pending = draft[field];
    if (pending !== undefined) {
      patch[field] = inputToLimit(pending);
    }
  }
  if (draft.is_active !== undefined) {
    patch.is_active = draft.is_active;
  }
  return patch;
}

/**
 * The threshold editor, backed by `feature_threshold_rules`.
 *
 * Storage keeps one global rule per feature plus optional per-channel
 * overrides, and that is exactly what this table shows: a global row, with any
 * override nested beneath the feature it overrides. Channels without an
 * override inherit — there is no row to edit for them, which is the point.
 */
export function ThresholdRulesSection() {
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole(ADMIN_ROLES);

  const {
    rules,
    ruleTypes,
    isLoading,
    isError,
    bulkUpdate,
    create,
    reset,
    remove,
    sensors,
    isSaving,
  } = useThresholdRules();

  const [drafts, setDrafts] = useState<Record<string, LimitDraft>>({});

  const sensorsById = useMemo(
    () => new Map(sensors.map((sensor) => [sensor.id, sensor])),
    [sensors]
  );

  const machineNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const sensor of sensors) {
      if (sensor.equipment_id && sensor.machine_name) {
        map.set(sensor.equipment_id, sensor.machine_name);
      }
    }
    return map;
  }, [sensors]);

  /** Global rule first, then its overrides narrowest scope first. */
  const groups = useMemo(() => {
    const byCode = new Map<string, { global: ThresholdRule | null; overrides: ThresholdRule[] }>();
    for (const rule of rules) {
      const entry = byCode.get(rule.feature_code) ?? { global: null, overrides: [] };
      if (isGlobalRule(rule)) {
        entry.global = rule;
      } else {
        entry.overrides.push(rule);
      }
      byCode.set(rule.feature_code, entry);
    }
    for (const entry of byCode.values()) {
      entry.overrides.sort(
        (a, b) => scopeRank(a) - scopeRank(b) || (a.channel ?? -1) - (b.channel ?? -1)
      );
    }
    return Array.from(byCode.entries()).map(([code, entry]) => ({ code, ...entry }));
  }, [rules]);

  const dirtyIds = useMemo(
    () => Object.keys(drafts).filter((id) => Object.keys(drafts[id]).length > 0),
    [drafts]
  );

  const errorsById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const rule of rules) {
      const message = validateRow(rule, drafts[rule.id]);
      if (message) map[rule.id] = message;
    }
    return map;
  }, [rules, drafts]);

  const setField = useCallback((ruleId: string, field: ThresholdLimitField, raw: string) => {
    setDrafts((prev) => ({ ...prev, [ruleId]: { ...prev[ruleId], [field]: raw } }));
  }, []);

  const setActive = useCallback((ruleId: string, isActive: boolean) => {
    setDrafts((prev) => ({ ...prev, [ruleId]: { ...prev[ruleId], is_active: isActive } }));
  }, []);

  const clearDraft = useCallback((ruleId: string) => {
    setDrafts((prev) => {
      if (!prev[ruleId]) return prev;
      const next = { ...prev };
      delete next[ruleId];
      return next;
    });
  }, []);

  const handleSave = useCallback(async () => {
    const blocked = dirtyIds.filter((id) => errorsById[id]);
    if (blocked.length > 0) {
      showToast("Fix the highlighted limits before saving.", "error");
      return;
    }

    const items = dirtyIds
      .map((id) => rules.find((rule) => rule.id === id))
      .filter((rule): rule is ThresholdRule => Boolean(rule))
      .map((rule) => draftToPatch(rule, drafts[rule.id]));

    if (items.length === 0) return;

    try {
      await bulkUpdate.mutateAsync(items);
      setDrafts({});
      showToast(
        `Saved ${items.length} threshold rule${items.length === 1 ? "" : "s"}.`,
        "success"
      );
    } catch {
      showToast("Could not save threshold rules.", "error");
    }
  }, [bulkUpdate, dirtyIds, drafts, errorsById, rules, showToast]);

  const handleReset = useCallback(
    async (rule: ThresholdRule) => {
      clearDraft(rule.id);
      try {
        await reset.mutateAsync(rule.id);
        showToast("Restored the factory limits for this rule.", "success");
      } catch {
        showToast("Could not restore the factory limits.", "error");
      }
    },
    [clearDraft, reset, showToast]
  );

  const handleRemoveOverride = useCallback(
    async (rule: ThresholdRule) => {
      clearDraft(rule.id);
      try {
        await remove.mutateAsync(rule.id);
        showToast("Override removed — this scope follows the broader rule again.", "success");
      } catch {
        showToast("Could not remove the override.", "error");
      }
    },
    [clearDraft, remove, showToast]
  );

  const handleAddOverride = useCallback(
    async (featureCode: string, scope: { channelNo?: number; sensorId?: string }) => {
      const sensorLabel = scope.sensorId
        ? sensorsById.get(scope.sensorId)?.label ?? "this sensor"
        : null;
      try {
        await create.mutateAsync({
          feature_code: featureCode,
          channel: scope.channelNo === undefined ? null : displayChannelToApi(scope.channelNo),
          sensor_id: scope.sensorId ?? null,
        });
        showToast(
          sensorLabel
            ? `Added a limit for ${sensorLabel}.`
            : `Added a CH-${scope.channelNo} override.`,
          "success"
        );
      } catch {
        showToast("Could not add the override.", "error");
      }
    },
    [create, sensorsById, showToast]
  );

  if (isLoading) {
    return (
      <SettingsSectionCard
        title="Threshold Rules"
        description="Alarm limits applied to every analysed measurement."
        icon={<Gauge size={22} strokeWidth={2} />}
      >
        <div className="flex items-center gap-g2 py-g4 text-sm text-muted-foreground">
          <Loader2 size={18} className="animate-spin text-brand" />
          Loading threshold rules…
        </div>
      </SettingsSectionCard>
    );
  }

  if (isError) {
    return (
      <SettingsSectionCard
        title="Threshold Rules"
        description="Alarm limits applied to every analysed measurement."
        icon={<Gauge size={22} strokeWidth={2} />}
      >
        <p className="py-g3 text-sm font-semibold text-destructive">
          Unable to load threshold rules.
        </p>
      </SettingsSectionCard>
    );
  }

  const renderRow = (rule: ThresholdRule, featureCode: string, isOverride: boolean) => {
    const draft = drafts[rule.id];
    const rowError = errorsById[rule.id];
    const typeInfo = ruleTypes[rule.rule_type];
    const uses: ThresholdLimitField[] = typeInfo?.uses ?? ["normal_max", "warning_max"];
    const isDirty = Boolean(draft && Object.keys(draft).length > 0);
    const isActive = draft?.is_active ?? rule.is_active;

    return (
      <tr
        key={rule.id}
        className={cn(
          "border-b border-border last:border-b-0 transition-colors hover:bg-warm/60",
          isDirty && "bg-signal-light/5",
          rowError && "bg-destructive/[0.03]"
        )}
      >
        <td className="px-g4 py-g2 whitespace-nowrap">
          {isOverride ? (
            <span className="pl-g3 text-muted-foreground">&#8627;</span>
          ) : (
            <span className="font-medium text-foreground">
              {rule.feature_name ?? rule.feature_code}
            </span>
          )}
        </td>
        <td className="px-3 py-2.5 whitespace-nowrap">
          {isOverride ? (
            <span className="font-bold text-brand">
              {scopeText(rule, sensorsById, machineNameById)}
            </span>
          ) : (
            <span className="text-muted-foreground">All sensors · All channels</span>
          )}
        </td>
        <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">
          <span title={typeInfo?.description}>{typeInfo?.label ?? rule.rule_type}</span>
          {rule.unit ? <span className="ml-1 text-xs">({rule.unit})</span> : null}
        </td>
        {LIMIT_FIELDS.map((field) => (
          <td key={field} className="px-3 py-2.5">
            {uses.includes(field) ? (
              <input
                type="number"
                step="any"
                className={cn(
                  analysisSelectClass,
                  "w-28 text-sm py-1.5",
                  rowError && "border-destructive/40"
                )}
                value={draft?.[field] ?? limitToInput(rule[field])}
                disabled={!canEdit || isSaving}
                placeholder="—"
                aria-label={`${rule.feature_name ?? rule.feature_code} ${LIMIT_HEADERS[field]}`}
                onChange={(event) => setField(rule.id, field, event.target.value)}
              />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </td>
        ))}
        <td className="px-3 py-2.5">
          <ToggleSwitch
            id={`threshold-rule-active-${rule.id}`}
            checked={isActive}
            disabled={!canEdit || isSaving}
            onChange={(next) => setActive(rule.id, next)}
          />
        </td>
        <td className="px-g4 py-g2">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              {isOverride ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 size={14} />}
                  disabled={!canEdit || isSaving}
                  onClick={() => handleRemoveOverride(rule)}
                >
                  Remove
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={<RotateCcw size={14} />}
                  disabled={!canEdit || isSaving || (rule.is_default && !isDirty)}
                  onClick={() => handleReset(rule)}
                >
                  Reset
                </Button>
              )}
              {!isOverride && canEdit && (
                <AddOverrideControl
                  featureCode={featureCode}
                  takenChannels={rules
                    .filter(
                      (r) =>
                        r.feature_code === featureCode &&
                        r.channel !== null &&
                        r.sensor_id === null
                    )
                    .map((r) => r.channel as number)}
                  takenSensorIds={rules
                    .filter((r) => r.feature_code === featureCode && r.sensor_id !== null)
                    .map((r) => r.sensor_id as string)}
                  sensors={sensors}
                  disabled={isSaving}
                  onAdd={handleAddOverride}
                />
              )}
            </div>
            {rowError && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive">
                <AlertTriangle size={12} />
                {rowError}
              </span>
            )}
          </div>
        </td>
      </tr>
    );
  };

  return (
    <SettingsSectionCard
      title="Threshold Rules"
      description="Alarm limits applied to every analysed measurement. A sensor or channel inherits the broader rule until you give it one of its own."
      icon={<Gauge size={22} strokeWidth={2} />}
      bodyClassName="p-0 sm:p-0"
    >
      <div className="flex flex-wrap items-center justify-between gap-g2 border-b border-border px-g4 py-g3">
        <p className="text-xs text-muted-foreground">
          Caution is the first limit a reading crosses; warning is the alarm limit.
          {!canEdit && " Administrator access is required to change them."}
        </p>
        <div className="flex items-center gap-g2">
          {dirtyIds.length > 0 && (
            <span className="text-xs font-medium text-signal">
              {dirtyIds.length} unsaved change{dirtyIds.length === 1 ? "" : "s"}
            </span>
          )}
          <Button
            type="button"
            variant="primary"
            size="sm"
            icon={isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            disabled={!canEdit || isSaving || dirtyIds.length === 0}
            onClick={handleSave}
          >
            Save Thresholds
          </Button>
        </div>
      </div>

      <div className="max-h-[34rem] overflow-x-auto overflow-y-auto rounded-b-xl">
        <table className="w-full min-w-[1120px] text-sm">
          <thead className="sticky top-0 z-10 border-b border-border bg-surface/95 backdrop-blur-sm">
            <tr className="text-left">
              <th className="px-g4 py-g3 font-semibold text-muted-foreground">Parameter</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Scope</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Rule</th>
              {LIMIT_FIELDS.map((field) => (
                <th key={field} className="px-3 py-3 font-semibold text-muted-foreground">
                  {LIMIT_HEADERS[field]}
                </th>
              ))}
              <th className="px-3 py-3 font-semibold text-muted-foreground">Enabled</th>
              <th className="px-g4 py-g3 font-semibold text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <React.Fragment key={group.code}>
                {group.global && renderRow(group.global, group.code, false)}
                {group.overrides.map((override) => renderRow(override, group.code, true))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </SettingsSectionCard>
  );
}

interface AddOverrideControlProps {
  featureCode: string;
  takenChannels: number[];
  takenSensorIds: string[];
  sensors: ThresholdScopeSensor[];
  disabled: boolean;
  onAdd: (featureCode: string, scope: { channelNo?: number; sensorId?: string }) => void;
}

/**
 * Offers the scopes this feature does not already have a rule for.
 *
 * Channels and sensors sit in one control, grouped, because they are the same
 * decision from the operator's side: what is this limit about? A sensor that
 * already has its own limit for this feature is not offered again — the API
 * would refuse it as a duplicate, and an option that cannot be chosen is worse
 * than no option.
 */
function AddOverrideControl({
  featureCode,
  takenChannels,
  takenSensorIds,
  sensors,
  disabled,
  onAdd,
}: AddOverrideControlProps) {
  const availableChannels = Array.from(
    { length: VIBRATION_CHANNEL_COUNT },
    (_, i) => i + 1
  ).filter((channelNo) => !takenChannels.includes(displayChannelToApi(channelNo)));

  const availableSensors = sensors.filter((sensor) => !takenSensorIds.includes(sensor.id));

  if (availableChannels.length === 0 && availableSensors.length === 0) return null;

  return (
    <label className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Plus size={12} />
      <select
        className={cn(analysisSelectClass, "w-36 py-1 text-xs")}
        value=""
        disabled={disabled}
        aria-label={`Add a scoped limit for ${featureCode}`}
        onChange={(event) => {
          const raw = event.target.value;
          if (!raw) return;
          if (raw.startsWith("sensor:")) {
            onAdd(featureCode, { sensorId: raw.slice("sensor:".length) });
          } else {
            onAdd(featureCode, { channelNo: Number(raw) });
          }
        }}
      >
        <option value="">Add limit for…</option>
        {availableSensors.length > 0 && (
          <optgroup label="Sensor">
            {availableSensors.map((sensor) => (
              <option key={sensor.id} value={`sensor:${sensor.id}`}>
                {sensor.label}
              </option>
            ))}
          </optgroup>
        )}
        {availableChannels.length > 0 && (
          <optgroup label="Channel (all sensors)">
            {availableChannels.map((channelNo) => (
              <option key={channelNo} value={channelNo}>
                CH-{channelNo}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  );
}

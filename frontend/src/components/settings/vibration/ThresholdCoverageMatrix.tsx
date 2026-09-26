import React, { useMemo, useState } from "react";
import { Grid3X3 } from "lucide-react";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import {
  channelLabel,
  findThresholdRow,
  formatThresholdParameterLabel,
  getThresholdCoverageStatus,
} from "@/lib/vibration-settings-utils";
import {
  buildSensorCoverage,
  type ThresholdScopeLevel,
} from "@/lib/threshold-scope-coverage";
import { buildFeatureCodeMap } from "@/lib/threshold-rule-adapters";
import {
  THRESHOLD_PARAMETERS,
  VIBRATION_CHANNEL_COUNT,
  type ThresholdConfig,
  type ThresholdCoverageStatus,
} from "@/types/vibration-settings";
import type { ThresholdRule, ThresholdScopeSensor } from "@/types/thresholds";
import { cn } from "@/lib/utils";

const COVERAGE_STYLES: Record<
  ThresholdCoverageStatus,
  { cell: string; dot: string; label: string }
> = {
  saved: {
    cell: "bg-machine-healthy/12 border-machine-healthy/25 hover:bg-machine-healthy/18",
    dot: "bg-machine-healthy",
    label: "Saved",
  },
  incomplete: {
    cell: "bg-signal-light/15 border-signal-light/35 hover:bg-signal-light/22",
    dot: "bg-signal-light",
    label: "Incomplete",
  },
  disabled: {
    cell: "bg-brand/[0.06] border-brand/15 hover:bg-brand/[0.1]",
    dot: "bg-brand",
    label: "Disabled",
  },
  empty: {
    cell: "bg-muted/30 border-border hover:bg-muted/45",
    dot: "bg-muted-foreground/35",
    label: "Not Configured",
  },
};

/**
 * Where a sensor's limit comes from, in the order the backend resolves it.
 *
 * Only the first is the sensor's own. The remaining three are all inheritance,
 * and they are kept apart on purpose: "falls back to the global rule" and "is
 * covered by its machine's rule" are different answers to the question this
 * view exists to answer, and colouring them alike would hide the difference
 * the scoping was built for.
 */
const SCOPE_STYLES: Record<
  ThresholdScopeLevel,
  { cell: string; dot: string; label: string; hint: string }
> = {
  sensor: {
    cell: "bg-machine-healthy/12 border-machine-healthy/25 hover:bg-machine-healthy/18",
    dot: "bg-machine-healthy",
    label: "Own limit",
    hint: "a limit written for this sensor",
  },
  machine: {
    cell: "bg-brand/[0.1] border-brand/25 hover:bg-brand/[0.16]",
    dot: "bg-brand",
    label: "This machine",
    hint: "inherited from a limit written for this machine",
  },
  machine_type: {
    cell: "bg-signal-light/15 border-signal-light/35 hover:bg-signal-light/22",
    dot: "bg-signal-light",
    label: "Machine type",
    hint: "inherited from a limit written for this machine type",
  },
  global: {
    cell: "bg-muted/30 border-border hover:bg-muted/45",
    dot: "bg-muted-foreground/35",
    label: "Global fallback",
    hint: "no limit of its own — judged by the platform-wide rule",
  },
  none: {
    cell: "bg-destructive/[0.06] border-destructive/25 hover:bg-destructive/[0.1]",
    dot: "bg-destructive/70",
    label: "No rule",
    hint: "no rule at any scope — nothing grades this feature",
  },
};

const SCOPE_ORDER: ThresholdScopeLevel[] = [
  "sensor",
  "machine",
  "machine_type",
  "global",
  "none",
];

type CoverageView = "channel" | "sensor";

interface ThresholdCoverageMatrixProps {
  thresholds: ThresholdConfig[];
  /** Rules as stored, carrying the scope each was written at. */
  rules?: ThresholdRule[];
  /** Every sensor, including those with no rule of their own. */
  sensors?: ThresholdScopeSensor[];
}

export function ThresholdCoverageMatrix({
  thresholds,
  rules = [],
  sensors = [],
}: ThresholdCoverageMatrixProps) {
  const [view, setView] = useState<CoverageView>("channel");
  const channels = Array.from({ length: VIBRATION_CHANNEL_COUNT }, (_, i) => i + 1);

  // Columns for the sensor view. The catalogue keys and the storage codes are
  // not the same string — the FFT band carries its band in the code — so the
  // mapping is learned from the rules and the catalogue supplies the order and
  // the labels.
  const columns = useMemo(() => {
    const codeByKey = buildFeatureCodeMap(rules);
    return THRESHOLD_PARAMETERS.map((param) => ({
      key: param.id,
      code: codeByKey.get(param.id),
      label: formatThresholdParameterLabel(param.id),
    })).filter((column): column is { key: typeof column.key; code: string; label: string } =>
      Boolean(column.code)
    );
  }, [rules]);

  const coverage = useMemo(
    () => buildSensorCoverage(rules, sensors, columns.map((column) => column.code)),
    [rules, sensors, columns]
  );

  const showSensors = view === "sensor";

  return (
    <SettingsSectionCard
      title="Threshold Coverage"
      description={
        showSensors
          ? "Which sensors carry limits of their own, and which are judged by a broader rule."
          : "Matrix view of threshold configuration status across all channels and parameters."
      }
      icon={<Grid3X3 size={22} strokeWidth={2} />}
    >
      <div className="mb-g3 flex flex-wrap items-center justify-between gap-g2">
        <div className="inline-flex rounded-md border border-border p-0.5">
          {(
            [
              ["channel", "By channel"],
              ["sensor", "By sensor"],
            ] as [CoverageView, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setView(value)}
              aria-pressed={view === value}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                view === value
                  ? "bg-brand text-white"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {showSensors && coverage.totalSensors > 0 && (
          <p className="text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">
              {coverage.sensorsWithOwnLimits} of {coverage.totalSensors}
            </span>{" "}
            sensors carry a limit of their own; the rest are judged by a broader rule.
          </p>
        )}
      </div>

      <div className="mb-g3 flex flex-wrap gap-x-g3 gap-y-g1 text-xs text-muted-foreground">
        {showSensors
          ? SCOPE_ORDER.map((level) => (
              <span
                key={level}
                className="inline-flex items-center gap-1.5"
                title={SCOPE_STYLES[level].hint}
              >
                <span className={cn("h-2 w-2 rounded-full", SCOPE_STYLES[level].dot)} />
                {SCOPE_STYLES[level].label}
              </span>
            ))
          : (Object.keys(COVERAGE_STYLES) as ThresholdCoverageStatus[]).map((status) => (
              <span key={status} className="inline-flex items-center gap-1.5">
                <span className={cn("h-2 w-2 rounded-full", COVERAGE_STYLES[status].dot)} />
                {COVERAGE_STYLES[status].label}
              </span>
            ))}
      </div>

      <div className="max-h-[32rem] overflow-auto rounded-md border border-border border-l-2 border-l-signal-light">
        <table className="w-full min-w-[880px] text-xs">
          <thead className="sticky top-0 z-20">
            <tr className="border-b border-border bg-surface/95">
              <th className="sticky left-0 z-30 bg-surface/95 px-3 py-2.5 text-left font-semibold text-muted-foreground border-r border-border">
                {showSensors ? "Sensor" : "Channel"}
              </th>
              {(showSensors
                ? columns
                : THRESHOLD_PARAMETERS.map((param) => ({
                    key: param.id,
                    label: formatThresholdParameterLabel(param.id),
                  }))
              ).map((column) => (
                <th
                  key={column.key}
                  className="bg-surface/95 px-2 py-2.5 text-center font-semibold text-muted-foreground whitespace-nowrap"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {showSensors
              ? coverage.rows.map((row) => (
                  <tr key={row.sensor.id} className="border-b border-border last:border-b-0">
                    <td
                      className="sticky left-0 z-10 bg-white px-3 py-2 border-r border-border whitespace-nowrap"
                      title={row.sensor.label}
                    >
                      <span className="font-semibold text-brand">
                        {row.sensor.machine_name ?? "Unassigned"}
                      </span>
                      <span className="ml-1.5 text-muted-foreground">
                        {row.sensor.label.includes(" — ")
                          ? row.sensor.label.split(" — ").slice(1).join(" — ")
                          : row.sensor.label}
                      </span>
                    </td>
                    {columns.map((column) => {
                      const cell =
                        row.cells[column.code] ?? { level: "none" as const, rule: null };
                      const styles = SCOPE_STYLES[cell.level];
                      return (
                        <td key={column.key} className="px-1.5 py-1.5">
                          <div
                            className={cn(
                              "flex h-9 items-center justify-center rounded-md border transition-colors",
                              styles.cell
                            )}
                            title={`${row.sensor.label} · ${column.label}: ${styles.label} — ${styles.hint}`}
                          >
                            <span className={cn("h-2.5 w-2.5 rounded-full", styles.dot)} />
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))
              : channels.map((channelNo) => (
                  <tr key={channelNo} className="border-b border-border last:border-b-0">
                    <td className="sticky left-0 z-10 bg-white px-3 py-2 font-bold text-brand border-r border-border whitespace-nowrap">
                      {channelLabel(channelNo)}
                    </td>
                    {THRESHOLD_PARAMETERS.map((param) => {
                      const row = findThresholdRow(thresholds, channelNo, param.id);
                      const status = row ? getThresholdCoverageStatus(row) : "empty";
                      const styles = COVERAGE_STYLES[status];

                      return (
                        <td key={param.id} className="px-1.5 py-1.5">
                          <div
                            className={cn(
                              "flex h-9 items-center justify-center rounded-md border transition-colors",
                              styles.cell
                            )}
                            title={`${channelLabel(channelNo)} · ${param.label}: ${styles.label}`}
                          >
                            <span className={cn("h-2.5 w-2.5 rounded-full", styles.dot)} />
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {showSensors && coverage.totalSensors === 0 && (
        <p className="py-g3 text-sm text-muted-foreground">
          No sensors are configured yet, so there is nothing to scope a limit to.
        </p>
      )}
    </SettingsSectionCard>
  );
}

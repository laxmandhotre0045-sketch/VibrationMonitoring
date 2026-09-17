import React, { useState } from "react";
import { RefreshCw, ChevronDown } from "lucide-react";
import type { Baseline } from "@/types/baseline";
import type { FeatureCompareItem } from "@/types/features";
import { formatDifferencePercent } from "@/lib/feature-api-normalize";
import {
  formatCompareValue,
  groupFeatureCompareItems,
} from "@/lib/feature-display";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { FeatureStatusBadge } from "./FeatureStatusBadge";
import { FeatureStatusTableSkeleton } from "./FeatureStatusTable";
import { cn } from "@/lib/utils";

interface FeatureComparisonSectionProps {
  items: FeatureCompareItem[];
  baselineOptions: Baseline[];
  selectedBaselineId: string;
  onBaselineChange: (baselineId: string) => void;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  className?: string;
}

function compareRowClass(status: FeatureCompareItem["status"]): string {
  if (status === "critical") return "bg-destructive/5";
  if (status === "warning") return "bg-signal-light/10";
  return "";
}

function CompareCategorySection({
  title,
  items,
}: {
  title: string;
  items: FeatureCompareItem[];
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 bg-surface/60 px-3 py-2.5 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
          {title}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-3 py-2 font-semibold text-muted-foreground">Feature</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Measured Value</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Baseline Value</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Difference (%)</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.feature_key ?? item.feature}
                className={cn(
                  "border-b border-border last:border-b-0 hover:bg-warm/40 transition-colors",
                  compareRowClass(item.status)
                )}
              >
                <td className="px-3 py-2.5 font-medium text-foreground">{item.feature}</td>
                <td className="px-3 py-2.5 font-semibold text-foreground">
                  {formatCompareValue(item.upload_value, item.unit)}
                </td>
                <td className="px-3 py-2.5 text-foreground">
                  {formatCompareValue(item.baseline_value, item.unit)}
                </td>
                <td className="px-3 py-2.5 font-semibold text-brand">
                  {formatDifferencePercent(item.difference_percent)}
                </td>
                <td className="px-3 py-2.5">
                  <FeatureStatusBadge status={item.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function FeatureComparisonSection({
  items,
  baselineOptions,
  selectedBaselineId,
  onBaselineChange,
  isLoading,
  error,
  onRetry,
  className,
}: FeatureComparisonSectionProps) {
  const groups = groupFeatureCompareItems(items);

  return (
    <section className={cn("space-y-g3", className)}>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h3 className="text-sm font-bold text-foreground">Feature Comparison vs Baseline</h3>
        {baselineOptions.length > 0 && (
          <div className="flex items-center gap-2 min-w-[220px]">
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground shrink-0">
              Baseline
            </label>
            <select
              className={analysisSelectClass}
              value={selectedBaselineId}
              onChange={(e) => onBaselineChange(e.target.value)}
            >
              <option value="">Select baseline…</option>
              {baselineOptions.map((baseline) => (
                <option key={baseline.id} value={baseline.id}>
                  {baseline.name}
                  {baseline.is_primary ? " (primary)" : ""}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!selectedBaselineId && (
        <p className="text-sm text-muted-foreground">
          Select a baseline to compare upload features.
        </p>
      )}

      {selectedBaselineId && isLoading && <FeatureStatusTableSkeleton />}

      {selectedBaselineId && !isLoading && !!error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-g4 py-g3">
          <p className="text-sm font-semibold text-destructive">
            Unable to load feature comparison data.
          </p>
          <Button
            size="sm"
            variant="secondary"
            className="mt-g3"
            icon={<RefreshCw size={14} />}
            onClick={onRetry}
          >
            Retry
          </Button>
        </div>
      )}

      {selectedBaselineId && !isLoading && !error && groups.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No feature comparison data returned for this baseline and channel.
        </p>
      )}

      {selectedBaselineId && !isLoading && !error && groups.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border border-l-2 border-l-signal-light shadow-sm">
          {groups.map((group) => (
            <CompareCategorySection key={group.category} title={group.label} items={group.items} />
          ))}
        </div>
      )}
    </section>
  );
}

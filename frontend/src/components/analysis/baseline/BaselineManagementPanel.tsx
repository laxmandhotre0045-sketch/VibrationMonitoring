import React, { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  ChevronDown,
  Loader2,
  RefreshCw,
  Search,
  Star,
} from "lucide-react";
import { setBaselinePrimary } from "@/api/baselines";
import type { Baseline, BaselineListResponse } from "@/types/baseline";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisCardPad,
  analysisInputClass,
  analysisSelectClass,
} from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { BaselineDetailCard } from "./BaselineDetailCard";
import {
  BaselinePlotStatusBadge,
  type BaselineListFilter,
  filterBaselines,
} from "./baseline-utils";
import { cn } from "@/lib/utils";

interface BaselineManagementPanelProps {
  sensorId: string;
  baselineList: BaselineListResponse | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  selectedBaselineId: string;
  loadedBaselineId: string;
  onLoadBaseline: (baseline: Baseline) => void;
  formatDateTime: (iso: string) => string;
  canWrite: boolean;
}

const FILTER_OPTIONS: { value: BaselineListFilter; label: string }[] = [
  { value: "all", label: "All Baselines" },
  { value: "primary", label: "Primary Baseline" },
  { value: "ready", label: "Ready" },
  { value: "pending", label: "Pending" },
  { value: "failed", label: "Failed" },
];

function BaselineListSkeleton() {
  return (
    <div className="space-y-g3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-white px-g4 py-g3 animate-pulse space-y-g2"
        >
          <div className="h-4 w-40 rounded bg-muted/60" />
          <div className="h-3 w-full max-w-md rounded bg-muted/40" />
          <div className="h-8 w-48 rounded bg-muted/50" />
        </div>
      ))}
    </div>
  );
}

export function BaselineManagementPanel({
  sensorId,
  baselineList,
  isLoading,
  error,
  onRetry,
  selectedBaselineId,
  loadedBaselineId,
  onLoadBaseline,
  formatDateTime,
  canWrite,
}: BaselineManagementPanelProps) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<BaselineListFilter>("all");
  const [detailBaselineId, setDetailBaselineId] = useState("");

  const setPrimaryMutation = useMutation({
    mutationFn: (baselineId: string) => setBaselinePrimary(baselineId, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["baseline-list", sensorId] });
      queryClient.invalidateQueries({ queryKey: ["primary-baseline", sensorId] });
    },
  });

  const filteredBaselines = useMemo(() => {
    if (!baselineList?.items.length) return [];
    return filterBaselines(baselineList.items, { search, filter, formatDateTime });
  }, [baselineList, search, filter, formatDateTime]);

  const detailBaseline =
    baselineList?.items.find((b) => b.id === detailBaselineId) ??
    baselineList?.items.find((b) => b.id === selectedBaselineId) ??
    null;

  if (!sensorId) return null;

  return (
    <GlassCard hover={false} className={analysisCardPad} delay={0.06}>
      <AnalysisSectionHeader
        icon={Bookmark}
        title="Baseline Management"
        subtitle="View, search, set primary, and load saved baselines for waveform, FFT, envelope, and trend analysis."
      />

      <div className="mt-g3 space-y-g3">
        <div className="flex flex-col lg:flex-row lg:items-center gap-3">
          <div className="relative flex-1 min-w-0">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <input
              type="search"
              placeholder="Search by baseline name or date..."
              className={cn(analysisInputClass, "pl-9")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className={cn(analysisSelectClass, "w-full lg:w-auto min-w-[180px]")}
            value={filter}
            onChange={(e) => setFilter(e.target.value as BaselineListFilter)}
          >
            {FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {isLoading && <BaselineListSkeleton />}

        {!isLoading && !!error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-g4 py-g3">
            <p className="text-sm font-semibold text-destructive">
              Unable to load baselines for this sensor.
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

        {!isLoading && !error && (baselineList?.total ?? 0) === 0 && (
          <div className="rounded-xl border border-dashed border-border bg-muted/10 px-g4 py-g6 text-center">
            <p className="text-sm font-semibold text-foreground">
              No baselines available for this sensor.
            </p>
            <p className="mt-g2 text-sm text-muted-foreground max-w-lg mx-auto">
              Select a timeline capture, open Detailed Analysis, and use Save as Baseline to create
              your first reference capture for health monitoring and comparison.
            </p>
          </div>
        )}

        {!isLoading && !error && (baselineList?.total ?? 0) > 0 && filteredBaselines.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No baselines match your search or filter.
          </p>
        )}

        {!isLoading && !error && filteredBaselines.length > 0 && (
          <div className="space-y-g3">
            {filteredBaselines.map((baseline) => {
              const isSelected = detailBaselineId
                ? baseline.id === detailBaselineId
                : baseline.id === selectedBaselineId;
              const isLoaded = baseline.id === loadedBaselineId;
              const isSettingPrimary =
                setPrimaryMutation.isPending && setPrimaryMutation.variables === baseline.id;

              return (
                <article
                  key={baseline.id}
                  className={cn(
                    "rounded-xl border bg-white px-g4 py-g3 shadow-sm transition-all duration-300",
                    "hover:-translate-y-0.5 hover:shadow-md",
                    baseline.is_primary
                      ? "border-signal-light/50 border-l-2 border-l-signal-light bg-signal-light/5"
                      : "border-border border-l-2 border-l-signal-light",
                    isSelected && "ring-2 ring-signal-light/40"
                  )}
                >
                  <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-g3">
                    <button
                      type="button"
                      className="text-left flex-1 min-w-0"
                      onClick={() => setDetailBaselineId(baseline.id)}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-base font-bold text-foreground">{baseline.name}</h4>
                        {baseline.is_primary && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-signal-light/40 bg-signal-light/15 px-2.5 py-0.5 text-xs font-semibold text-signal-dark">
                            <Star size={12} className="fill-current" />
                            Primary Baseline
                          </span>
                        )}
                        {isLoaded && (
                          <span className="inline-flex items-center rounded-full border border-brand/30 bg-brand/10 px-2.5 py-0.5 text-xs font-semibold text-brand">
                            Loaded for Analysis
                          </span>
                        )}
                      </div>
                      <div className="mt-g2 flex flex-wrap items-center gap-x-g3 gap-y-g1 text-sm text-muted-foreground">
                        <span>Created: {formatDateTime(baseline.created_at)}</span>
                        <span>Samples: {baseline.sample_count.toLocaleString()}</span>
                        <span>Channels: {baseline.channel_count}</span>
                        <span className="inline-flex items-center gap-1.5">
                          Plots: <BaselinePlotStatusBadge status={baseline.plots_status} />
                        </span>
                      </div>
                    </button>

                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      {canWrite && !baseline.is_primary && (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={setPrimaryMutation.isPending}
                          icon={
                            isSettingPrimary ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Star size={14} />
                            )
                          }
                          onClick={() => setPrimaryMutation.mutate(baseline.id)}
                        >
                          Set as Primary
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant={isLoaded ? "secondary" : "primary"}
                        onClick={() => {
                          setDetailBaselineId(baseline.id);
                          onLoadBaseline(baseline);
                        }}
                      >
                        Load for Analysis
                      </Button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {detailBaseline && !isLoading && !error && (
          <details className="group" open>
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-foreground">
              <ChevronDown
                size={16}
                className="transition-transform group-open:rotate-180 text-muted-foreground"
              />
              Selected Baseline Details
            </summary>
            <div className="mt-g3">
              <BaselineDetailCard baseline={detailBaseline} formatDateTime={formatDateTime} />
            </div>
          </details>
        )}
      </div>
    </GlassCard>
  );
}

import React, { useState } from "react";
import { TrendingUp } from "lucide-react";
import { CompactDateRangeBar } from "@/components/analysis/CompactDateRangeBar";
import { HealthChannelSelector } from "@/components/analysis/health/HealthChannelSelector";
import { HealthMetricCard } from "@/components/analysis/health/HealthMetricCard";
import { analysisBodyStack, analysisGridGap } from "@/components/analysis/analysis-layout";
import { useHistoricalTrendData } from "@/hooks/useHistoricalTrendData";
import { cn } from "@/lib/utils";

interface TrendAnalysisTabProps {
  sensorId: string;
  samplingRateHz: number;
  primaryBaselineId?: string | null;
}

export function TrendAnalysisTab({
  sensorId,
  samplingRateHz,
  primaryBaselineId,
}: TrendAnalysisTabProps) {
  const [trendChannel, setTrendChannel] = useState(0);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [compareBaseline, setCompareBaseline] = useState(false);
  const [compareHistorical, setCompareHistorical] = useState(true);

  const enabled = !!sensorId;

  const { range, uploads, trendMetrics, isLoading } = useHistoricalTrendData({
    sensorId,
    channel: trendChannel,
    samplingRateHz,
    fromDate: fromDate || undefined,
    toDate: toDate || undefined,
    primaryBaselineId,
    compareBaseline,
    enabled,
  });

  const effectiveFrom = fromDate || range.fromDate;
  const effectiveTo = toDate || range.toDate;

  return (
    <div className={analysisBodyStack}>
      <p className="text-sm text-muted-foreground">
        Analyze how machine conditions change over time using historical captures in the selected range.
      </p>

      <HealthChannelSelector
        value={trendChannel}
        onChange={setTrendChannel}
        disabled={!enabled}
      />

      <CompactDateRangeBar
        fromDate={effectiveFrom}
        toDate={effectiveTo}
        onFromChange={setFromDate}
        onToChange={setToDate}
        disabled={!enabled}
      />

      <div className="flex flex-wrap items-center gap-4 rounded-md border border-border bg-surface/50 px-3 py-2">
        <label className="inline-flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-border"
            checked={compareHistorical}
            onChange={(e) => setCompareHistorical(e.target.checked)}
            disabled={!enabled}
          />
          <TrendingUp size={14} className="text-signal-dark" aria-hidden />
          Historical Comparison
        </label>
        <label className="inline-flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-border"
            checked={compareBaseline}
            onChange={(e) => setCompareBaseline(e.target.checked)}
            disabled={!enabled || !primaryBaselineId}
          />
          Baseline Comparison
          {!primaryBaselineId && (
            <span className="text-xs text-muted-foreground">(no primary baseline)</span>
          )}
        </label>
      </div>

      {!enabled && (
        <p className="text-sm text-muted-foreground">Select a sensor to load historical trends.</p>
      )}

      {enabled && isLoading && (
        <p className="text-sm text-muted-foreground">Loading historical trend data…</p>
      )}

      {enabled && !isLoading && uploads.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No captures found in the selected date range.
        </p>
      )}

      {enabled && !isLoading && compareHistorical && uploads.length > 0 && (
        <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
          {trendMetrics.map((metric) => (
            <HealthMetricCard
              key={`trend-${trendChannel}-${metric.key}`}
              metric={metric}
              channelLabel={`CH-${trendChannel + 1}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

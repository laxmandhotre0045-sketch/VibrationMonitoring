import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { TrendingUp } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { analysisCardPad, analysisSelectClass } from "@/components/analysis/analysis-layout";
import {
  projectFeatureTrend,
  trendLimitFor,
  TREND_HORIZON_DAYS,
  type AiCapture,
  type ResolvedLimit,
} from "@/lib/ai-diagnostics";
import {
  VIBRATION_FEATURE_CATALOG,
  formatFeatureUnit,
  type VibrationFeatureKey,
} from "@/lib/vibration-features";
import { ECHARTS_BRAND, baseAxisStyle } from "@/lib/echarts-theme";
import { cn } from "@/lib/utils";

/** Below this the straight line is describing scatter, not a trajectory. */
const WEAK_FIT_R2 = 0.3;

function formatValue(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000 || (value !== 0 && Math.abs(value) < 0.01)) {
    return value.toExponential(2);
  }
  return value.toFixed(3);
}

function formatDays(days: number): string {
  if (days < 1) return "under a day";
  if (days < 45) return `${Math.round(days)} days`;
  if (days < 365) return `${(days / 30.44).toFixed(1)} months`;
  return `${(days / 365).toFixed(1)} years`;
}

interface TrendForecastCardProps {
  series: AiCapture[];
  limits: Map<VibrationFeatureKey, ResolvedLimit>;
}

/**
 * Where one feature is heading, and when it would meet its limit.
 *
 * The fit quality travels with the projection on purpose — a straight line can
 * be drawn through any scatter, and a crossing date read off a weak fit is the
 * kind of number that gets a machine stripped for nothing.
 */
export function TrendForecastCard({ series, limits }: TrendForecastCardProps) {
  const available = useMemo(
    () =>
      VIBRATION_FEATURE_CATALOG.filter((def) =>
        series.some((c) => c.features[def.key] !== undefined)
      ),
    [series]
  );

  const [selected, setSelected] = useState<VibrationFeatureKey>("rms");
  const activeKey = available.some((d) => d.key === selected)
    ? selected
    : (available[0]?.key ?? "rms");

  const projection = useMemo(
    () => projectFeatureTrend(series, activeKey, trendLimitFor(limits.get(activeKey))),
    [series, activeKey, limits]
  );

  const option = useMemo<EChartsOption>(() => {
    if (!projection) return {};
    const axis = baseAxisStyle();
    const unit = formatFeatureUnit(projection.unit);

    return {
      grid: { left: 8, right: 22, top: 30, bottom: 28, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: ECHARTS_BRAND.plot,
        borderColor: ECHARTS_BRAND.amber,
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: ECHARTS_BRAND.blue, fontFamily: ECHARTS_BRAND.font, fontSize: 13 },
        confine: true,
        valueFormatter: (value: unknown) => formatValue(Number(value)),
      },
      legend: {
        top: 0,
        right: 0,
        icon: "roundRect",
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: ECHARTS_BRAND.muted, fontFamily: ECHARTS_BRAND.font, fontSize: 11 },
      },
      xAxis: { type: "time", ...axis, splitLine: { show: false } },
      yAxis: {
        type: "value",
        name: unit === "—" ? "" : unit,
        nameTextStyle: {
          color: ECHARTS_BRAND.muted,
          fontFamily: ECHARTS_BRAND.font,
          fontSize: 11,
        },
        scale: true,
        ...axis,
      },
      series: [
        {
          name: "Measured",
          type: "line",
          showSymbol: true,
          symbolSize: 6,
          data: projection.points.map((p) => [p.timeMs, p.value]),
          lineStyle: { color: ECHARTS_BRAND.blue, width: 2 },
          itemStyle: { color: ECHARTS_BRAND.blue },
        },
        {
          name: `${TREND_HORIZON_DAYS}-day projection`,
          type: "line",
          showSymbol: false,
          data: projection.fit.map((p) => [p.timeMs, p.value]),
          lineStyle: { color: ECHARTS_BRAND.orange, width: 2, type: "dashed" },
          itemStyle: { color: ECHARTS_BRAND.orange },
          markLine: projection.limit
            ? {
                silent: true,
                symbol: "none",
                label: {
                  formatter: projection.limit.label,
                  color: "#EF4444",
                  fontFamily: ECHARTS_BRAND.font,
                  fontSize: 10,
                  position: "insideEndTop",
                },
                data: [
                  {
                    yAxis: projection.limit.value,
                    lineStyle: { color: "#EF4444", type: "dashed", width: 1.5 },
                  },
                ],
              }
            : undefined,
        },
      ],
    };
  }, [projection]);

  const kpis = projection
    ? [
        {
          label: "Change per week",
          value:
            projection.changePerWeekPct === null
              ? "—"
              : `${projection.changePerWeekPct >= 0 ? "+" : ""}${projection.changePerWeekPct.toFixed(1)}%`,
          tone:
            projection.changePerWeekPct !== null && projection.changePerWeekPct > 5
              ? "text-machine-warning"
              : "text-foreground",
        },
        {
          label: "Fit quality (R²)",
          value: projection.r2.toFixed(2),
          tone: projection.r2 < WEAK_FIT_R2 ? "text-muted-foreground" : "text-foreground",
        },
        {
          label: `In ${TREND_HORIZON_DAYS} days`,
          value: formatValue(projection.projected),
          tone: "text-foreground",
        },
        {
          label: projection.limit ? `To ${projection.limit.label.toLowerCase()}` : "To limit",
          value: projection.daysToLimit === null ? "—" : formatDays(projection.daysToLimit),
          tone: projection.daysToLimit !== null ? "text-machine-critical" : "text-muted-foreground",
        },
      ]
    : [];

  return (
    <GlassCard className={analysisCardPad} delay={0.18}>
      <AnalysisSectionHeader
        icon={TrendingUp}
        title="Trend Projection"
        subtitle="A least-squares trajectory through the capture history, extended to the limit the threshold rules set for this channel."
      />

      <div className="mb-g3 flex flex-wrap items-center gap-g3">
        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Feature
        </label>
        <select
          className={cn(analysisSelectClass, "w-auto min-w-[200px]")}
          value={activeKey}
          onChange={(e) => setSelected(e.target.value as VibrationFeatureKey)}
          disabled={!available.length}
        >
          {available.map((def) => (
            <option key={def.key} value={def.key}>
              {def.label}
            </option>
          ))}
        </select>
      </div>

      {!projection ? (
        <p className="rounded-lg border border-border bg-warm px-g4 py-g3 text-sm text-muted-foreground">
          A projection needs at least three captures spread over time. Upload more data for this
          sensor on the Vibration Analysis page and the trajectory will appear here.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-g2 xl:grid-cols-4">
            {kpis.map((kpi) => (
              <div key={kpi.label} className="rounded-md border border-border bg-white px-g3 py-g2">
                <p className="text-[11px] font-semibold uppercase leading-none tracking-wide text-muted-foreground">
                  {kpi.label}
                </p>
                <p className={cn("mt-g1 text-base font-bold leading-tight", kpi.tone)}>
                  {kpi.value}
                </p>
              </div>
            ))}
          </div>

          <ReactECharts
            option={option}
            style={{ height: 280, width: "100%" }}
            opts={{ renderer: "canvas" }}
            notMerge
          />

          <p className="text-xs leading-relaxed text-muted-foreground">
            {projection.r2 < WEAK_FIT_R2
              ? "The captures scatter too widely for this line to carry a date — read it as a direction only."
              : projection.daysToLimit !== null
                ? `At the current rate ${projection.label} reaches the ${projection.limit?.label.toLowerCase()} in about ${formatDays(projection.daysToLimit)}.`
                : projection.limit
                  ? `${projection.label} is not trending toward the ${projection.limit.label.toLowerCase()} on the current slope.`
                  : "No absolute limit is configured for this feature, so the line is shown without a crossing point."}
          </p>
        </>
      )}
    </GlassCard>
  );
}

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { Radar } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { analysisCardPad } from "@/components/analysis/analysis-layout";
import { ANOMALY_MIN_HISTORY, type AnomalyLevel, type AnomalyPoint } from "@/lib/ai-diagnostics";
import { getFeatureDefinition } from "@/lib/vibration-features";
import { ECHARTS_BRAND, baseAxisStyle } from "@/lib/echarts-theme";
import { cn } from "@/lib/utils";

const LEVEL_COLOR: Record<AnomalyLevel, string> = {
  normal: "rgba(21, 54, 109, 0.35)",
  borderline: "#F5A623",
  anomalous: "#EF4444",
};

const LEVEL_LABEL: Record<AnomalyLevel, string> = {
  normal: "Within history",
  borderline: "Drifting",
  anomalous: "Outlier",
};

interface AnomalyTimelineCardProps {
  points: AnomalyPoint[];
}

/**
 * Novelty per capture, scored against only the captures that came before it.
 *
 * The bar height is a robust z-score, so the two reference lines are fixed: 2.5
 * is where a reading leaves the band its own history would predict, 4 is where
 * it stops being explainable as scatter.
 */
export function AnomalyTimelineCard({ points }: AnomalyTimelineCardProps) {
  const scored = points.filter((p) => p.score > 0);
  const flagged = points.filter((p) => p.level !== "normal");

  const option = useMemo<EChartsOption>(() => {
    const axis = baseAxisStyle();

    return {
      grid: { left: 8, right: 18, top: 28, bottom: 28, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: ECHARTS_BRAND.plot,
        borderColor: ECHARTS_BRAND.amber,
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: ECHARTS_BRAND.blue, fontFamily: ECHARTS_BRAND.font, fontSize: 13 },
        confine: true,
        formatter: (params: unknown) => {
          const list = params as { dataIndex: number }[];
          const point = points[list[0]?.dataIndex ?? 0];
          if (!point) return "";
          const driver = point.driver ? getFeatureDefinition(point.driver).label : "—";
          return [
            `<strong>${new Date(point.observedAt).toLocaleString()}</strong>`,
            `Novelty score: <strong>${point.score.toFixed(2)}</strong>`,
            `Largest mover: <strong>${driver}</strong>`,
            LEVEL_LABEL[point.level],
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: points.map((p) => new Date(p.observedAt).toLocaleDateString()),
        ...axis,
        splitLine: { show: false },
        axisLabel: { ...axis.axisLabel, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        name: "Novelty (σ)",
        nameTextStyle: {
          color: ECHARTS_BRAND.muted,
          fontFamily: ECHARTS_BRAND.font,
          fontSize: 11,
        },
        min: 0,
        ...axis,
      },
      series: [
        {
          type: "bar",
          data: points.map((p) => ({
            value: p.score,
            itemStyle: { color: LEVEL_COLOR[p.level], borderRadius: [3, 3, 0, 0] },
          })),
          barMaxWidth: 26,
          markLine: {
            silent: true,
            symbol: "none",
            label: {
              formatter: (item: { name?: string }) => item.name ?? "",
              color: ECHARTS_BRAND.muted,
              fontFamily: ECHARTS_BRAND.font,
              fontSize: 10,
              position: "insideEndTop",
            },
            data: [
              { yAxis: 2.5, name: "drift", lineStyle: { color: "#F5A623", type: "dashed" } },
              { yAxis: 4, name: "outlier", lineStyle: { color: "#EF4444", type: "dashed" } },
            ],
          },
        },
      ],
    };
  }, [points]);

  return (
    <GlassCard className={analysisCardPad} delay={0.14}>
      <AnalysisSectionHeader
        icon={Radar}
        title="Anomaly Timeline"
        subtitle="Each capture scored against the ones recorded before it, so a rising fault cannot quietly become its own normal."
      />

      {scored.length === 0 ? (
        <p className="rounded-lg border border-border bg-warm px-g4 py-g3 text-sm text-muted-foreground">
          Novelty scoring starts once this channel has {ANOMALY_MIN_HISTORY + 1} captures — there is
          not yet enough history to say what normal looks like for it.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-g3">
            {(["anomalous", "borderline", "normal"] as AnomalyLevel[]).map((level) => (
              <span key={level} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ backgroundColor: LEVEL_COLOR[level] }}
                />
                {LEVEL_LABEL[level]}
              </span>
            ))}
            <span
              className={cn(
                "ml-auto text-xs font-semibold",
                flagged.length ? "text-machine-warning" : "text-machine-healthy"
              )}
            >
              {flagged.length
                ? `${flagged.length} of ${points.length} captures flagged`
                : `No capture outside its own history`}
            </span>
          </div>

          <ReactECharts
            option={option}
            style={{ height: 240, width: "100%" }}
            opts={{ renderer: "canvas" }}
            notMerge
          />
        </>
      )}
    </GlassCard>
  );
}

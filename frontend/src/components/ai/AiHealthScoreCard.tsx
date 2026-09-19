import React from "react";
import { Gauge } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { analysisCardPad } from "@/components/analysis/analysis-layout";
import { HEALTH_BAND_LABEL, type HealthAssessment, type HealthBand } from "@/lib/ai-diagnostics";
import { STATUS_TONES, type StatusTone } from "@/lib/status-box";
import { StatusBadge, StatusRail } from "@/components/ui/StatusBox";
import { cn } from "@/lib/utils";

/** The page's own band, on the shared tone scale. */
const BAND_TONE: Record<HealthBand, StatusTone> = {
  healthy: "healthy",
  watch: "caution",
  warning: "warning",
  critical: "critical",
};

/** The gauge arc is an SVG stroke, which no background utility can paint. */
const BAND_STROKE: Record<HealthBand, string> = {
  healthy: "stroke-machine-healthy",
  watch: "stroke-brand",
  warning: "stroke-machine-warning",
  critical: "stroke-machine-critical",
};

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

interface AiHealthScoreCardProps {
  assessment: HealthAssessment;
  capturesAnalyzed: number;
  observedAt: string;
}

/**
 * The channel's condition score with the deductions that produced it.
 *
 * The drivers are listed rather than summarised: the score is a heuristic, and
 * an analyst who can see it was "-20 for one critical feature, -14 for a
 * misalignment pattern" can judge whether to trust it.
 */
export function AiHealthScoreCard({
  assessment,
  capturesAnalyzed,
  observedAt,
}: AiHealthScoreCardProps) {
  const tone = STATUS_TONES[BAND_TONE[assessment.band]];
  const dash = (assessment.score / 100) * CIRCUMFERENCE;

  return (
    <GlassCard className={cn(analysisCardPad, "relative overflow-hidden")} delay={0.06}>
      {/* The page's headline verdict, lit from the edge in its own colour. */}
      <StatusRail tone={BAND_TONE[assessment.band]} className="w-[4px]" />

      <AnalysisSectionHeader
        icon={Gauge}
        title="Condition Score"
        subtitle="Derived from the latest capture's graded features, the strongest fault pattern, and the drift against this sensor's own history."
      />

      <div className="flex flex-col gap-g4 sm:flex-row sm:items-center">
        <div className="relative shrink-0 self-center sm:self-auto">
          <svg width={128} height={128} viewBox="0 0 128 128" role="img" aria-label={`Condition score ${assessment.score} of 100`}>
            <circle
              cx={64}
              cy={64}
              r={RADIUS}
              fill="none"
              strokeWidth={10}
              className="stroke-border"
            />
            <circle
              cx={64}
              cy={64}
              r={RADIUS}
              fill="none"
              strokeWidth={10}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${CIRCUMFERENCE - dash}`}
              transform="rotate(-90 64 64)"
              className={cn(
                BAND_STROKE[assessment.band],
                "transition-[stroke-dasharray] duration-700 ease-out"
              )}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn("text-3xl font-bold leading-none", tone.text)}>
              {assessment.score}
            </span>
            <span className="mt-g1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              of 100
            </span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-g2">
            <StatusBadge tone={BAND_TONE[assessment.band]} className="px-2.5 py-1 text-xs">
              {HEALTH_BAND_LABEL[assessment.band]}
            </StatusBadge>
            <span className="text-xs text-muted-foreground">
              {capturesAnalyzed} capture{capturesAnalyzed === 1 ? "" : "s"} analysed · latest{" "}
              {new Date(observedAt).toLocaleString()}
            </span>
          </div>

          <p className="mt-g2 text-sm leading-relaxed text-foreground">{assessment.headline}</p>

          {assessment.drivers.length > 0 && (
            <ul className="mt-g3 space-y-g1">
              {assessment.drivers.map((driver) => (
                <li
                  key={driver.label}
                  className="flex items-center justify-between gap-g3 rounded-md border border-border bg-white px-g3 py-1.5"
                >
                  <span className="min-w-0 text-sm text-foreground">{driver.label}</span>
                  <span className="shrink-0 text-sm font-bold text-machine-critical">
                    −{driver.penalty}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </GlassCard>
  );
}

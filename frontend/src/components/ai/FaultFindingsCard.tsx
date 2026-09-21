import React from "react";
import { BrainCircuit, CheckCircle2, Wrench } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { analysisCardPad } from "@/components/analysis/analysis-layout";
import type { FaultFinding, FaultSeverity } from "@/lib/ai-diagnostics";
import { STATUS_TONES, type StatusTone } from "@/lib/status-box";
import { StatusBadge, StatusRail } from "@/components/ui/StatusBox";
import { cn } from "@/lib/utils";

const SEVERITY_LABEL: Record<FaultSeverity, string> = {
  severe: "Severe",
  elevated: "Elevated",
  watch: "Watch",
};

/** A finding's severity on the shared tone scale. */
const SEVERITY_TONE: Record<FaultSeverity, StatusTone> = {
  severe: "critical",
  elevated: "warning",
  watch: "caution",
};

/** The confidence bar is the tone as a solid fill. */
const SEVERITY_BAR: Record<FaultSeverity, string> = {
  severe: "bg-machine-critical",
  elevated: "bg-machine-warning",
  watch: "bg-brand/60",
};

interface FaultFindingsCardProps {
  findings: FaultFinding[];
  /** Fewer captures than this and the history-based rules stay quiet. */
  hasHistory: boolean;
}

/**
 * The ranked fault patterns, each opened up into the numbers it fired on.
 *
 * Confidence is shown as a bar and a percentage because the rules are scored,
 * not binary — two patterns often fire together (looseness sitting on top of
 * misalignment is the common pair) and the order matters more than the verdict.
 */
export function FaultFindingsCard({ findings, hasHistory }: FaultFindingsCardProps) {
  return (
    <GlassCard className={analysisCardPad} delay={0.1}>
      <AnalysisSectionHeader
        icon={BrainCircuit}
        title="Fault Pattern Diagnosis"
        subtitle="Running-speed harmonics, envelope and impulsiveness matched against the classical machinery fault signatures."
      />

      {findings.length === 0 ? (
        <div className="flex items-start gap-g3 rounded-lg border border-machine-healthy/25 bg-machine-healthy/5 px-g4 py-g3">
          <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-machine-healthy" />
          <div>
            <p className="text-sm font-semibold text-foreground">No fault pattern matched</p>
            <p className="mt-g1 text-sm text-muted-foreground">
              {hasHistory
                ? "Harmonic ratios, envelope energy and impulsiveness all sit inside the normal band for this channel."
                : "Harmonic ratios sit in the normal band. The history-based rules — bearing wear, looseness and broadband rise — need a few more captures on this channel before they can fire."}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-g3">
          {findings.map((finding) => {
            const tone = STATUS_TONES[SEVERITY_TONE[finding.severity]];
            const pct = Math.round(finding.confidence * 100);

            return (
              <article
                key={finding.id}
                className={cn(
                  "relative overflow-hidden rounded-lg border border-border bg-white p-g4 pl-g5",
                  "shadow-[0_2px_10px_rgba(21,54,109,0.05)]",
                  // The wash rides on the card's own background rather than an
                  // overlay, which would tint the text sitting under it.
                  tone.wash
                )}
              >
                {/* Severity lights the card from its edge, so a stack of
                    findings can be ranked without reading a single word. */}
                <StatusRail tone={SEVERITY_TONE[finding.severity]} className="w-[4px]" />

                <div className="flex flex-wrap items-center justify-between gap-g2">
                  <div className="flex items-center gap-g2">
                    <h3 className="text-base font-bold text-foreground">{finding.label}</h3>
                    <StatusBadge tone={SEVERITY_TONE[finding.severity]}>
                      {SEVERITY_LABEL[finding.severity]}
                    </StatusBadge>
                  </div>
                  <span className="text-sm font-bold text-foreground">{pct}% confidence</span>
                </div>

                <div className="mt-g2 h-1.5 w-full overflow-hidden rounded-full bg-muted/40">
                  <div
                    className={cn(
                      "h-full rounded-full transition-[width] duration-700",
                      SEVERITY_BAR[finding.severity]
                    )}
                    style={{ width: `${pct}%` }}
                  />
                </div>

                <p className="mt-g3 text-sm leading-relaxed text-foreground">{finding.summary}</p>

                <dl className="mt-g3 grid grid-cols-1 gap-g2 sm:grid-cols-2 xl:grid-cols-4">
                  {finding.evidence.map((item) => (
                    <div
                      key={item.label}
                      className="rounded-md border border-border bg-warm px-g3 py-g2"
                    >
                      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {item.label}
                      </dt>
                      <dd className="mt-g1 text-base font-bold leading-tight text-foreground">
                        {item.value}
                      </dd>
                      <dd className="mt-g1 text-xs leading-snug text-muted-foreground">
                        {item.note}
                      </dd>
                    </div>
                  ))}
                </dl>

                <div className="mt-g3 flex items-start gap-g2 rounded-r-md border border-border border-l-2 border-l-signal-light bg-warm px-g3 py-g2">
                  <Wrench size={14} className="mt-0.5 shrink-0 text-signal-dark" />
                  <div>
                    <p className="text-sm leading-relaxed text-foreground">
                      {finding.recommendation}
                    </p>
                    <p className="mt-g1 text-xs text-muted-foreground">
                      Rule basis: {finding.basis}
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}

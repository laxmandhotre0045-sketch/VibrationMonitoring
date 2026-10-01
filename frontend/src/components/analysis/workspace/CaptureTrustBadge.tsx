import React from "react";
import { AlertTriangle, HelpCircle, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import type { TrustLevel } from "@/types/features";
import { cn } from "@/lib/utils";

/**
 * What each level means in the analyst's terms, not the engine's.
 *
 * `null` is deliberately in this map. A capture nothing has assessed is
 * unexamined, not trustworthy, and the badge says so rather than staying blank
 * — a missing badge reads as "fine", which is the exact mistake this component
 * exists to prevent.
 */
const TRUST_STYLES: Record<
  TrustLevel | "unassessed",
  { label: string; meaning: string; box: string; text: string; Icon: typeof ShieldCheck }
> = {
  High: {
    label: "Trusted",
    meaning: "Every quality check passed. Read these plots at face value.",
    box: "border-machine-healthy/30 bg-machine-healthy/10",
    text: "text-machine-healthy",
    Icon: ShieldCheck,
  },
  Medium: {
    label: "Reduced trust",
    meaning: "Some checks failed. Treat small differences with caution.",
    box: "border-signal-light/40 bg-signal-light/10",
    text: "text-signal-dark",
    Icon: ShieldAlert,
  },
  Low: {
    label: "Low trust",
    meaning: "Serious quality problems. Confirm anything you conclude from another capture.",
    box: "border-destructive/30 bg-destructive/[0.07]",
    text: "text-destructive",
    Icon: ShieldAlert,
  },
  Invalid: {
    label: "Not usable",
    meaning: "This capture failed a check that makes its numbers meaningless. Do not draw conclusions from it.",
    box: "border-destructive/45 bg-destructive/[0.12]",
    text: "text-destructive",
    Icon: ShieldX,
  },
  unassessed: {
    label: "Not assessed",
    meaning: "No quality check has run on this capture. That is not the same as passing — nothing has been verified.",
    box: "border-border bg-muted/30",
    text: "text-muted-foreground",
    Icon: HelpCircle,
  },
};

/** Check names as an analyst would read them, not as the engine stores them. */
export const CHECK_LABELS: Record<string, string> = {
  missing_data: "Missing samples",
  clipping: "Clipped peaks",
  saturation: "Sensor saturated",
  loose_sensor: "Loose sensor",
  unstable_speed: "Unstable shaft speed",
  bias_drift: "Bias drift",
  noise_floor: "High noise floor",
  dc_offset: "DC offset",
  // Section 21.1's remaining checks, added to the engine after an audit
  // against the requirement. A test here fails when the backend can report
  // a check this map has no words for — which is how these arrived, rather
  // than by anybody noticing the screen had started showing raw slugs.
  low_signal: "Too little signal",
  wrong_rpm: "Speed disagrees with nameplate",
  wrong_machine_state: "State disagrees with vibration",
  sensor_temperature: "Sensor temperature",
  packet_loss: "Readings lost in transit",
  communication: "Gateway link down",
};

export function formatCheckName(name: string): string {
  const known = CHECK_LABELS[name];
  if (known) return known;
  // An unknown check still has to read as words. A raw slug on screen is the
  // engine leaking through, but hiding it would hide a real finding.
  return name
    .replace(/[_-]+/g, " ")
    .replace(/^\w/, (character) => character.toUpperCase());
}

interface CaptureTrustBadgeProps {
  trustLevel: TrustLevel | null;
  failedChecks: string[];
  notAssessedChecks?: string[];
  /** While the verdict is still loading, say nothing rather than "unassessed". */
  isLoading?: boolean;
  className?: string;
}

/**
 * The capture's trust verdict, shown beside the capture selector.
 *
 * Placed where the capture is chosen rather than down among the plots, so the
 * analyst learns the data is untrustworthy before reading anything from it
 * instead of after reaching a conclusion.
 */
export function CaptureTrustBadge({
  trustLevel,
  failedChecks,
  notAssessedChecks = [],
  isLoading = false,
  className,
}: CaptureTrustBadgeProps) {
  if (isLoading) {
    return (
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/20 px-2.5 py-1",
          className
        )}
      >
        <span className="h-3.5 w-3.5 animate-pulse rounded-full bg-muted-foreground/30" />
        <span className="text-xs text-muted-foreground">Checking quality…</span>
      </div>
    );
  }

  const styles = TRUST_STYLES[trustLevel ?? "unassessed"];
  const { Icon } = styles;
  const hasFindings = failedChecks.length > 0 || notAssessedChecks.length > 0;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span
        className={cn(
          "inline-flex w-fit items-center gap-1.5 rounded-md border px-2.5 py-1",
          styles.box
        )}
        title={styles.meaning}
      >
        <Icon size={14} className={styles.text} strokeWidth={2.25} aria-hidden />
        <span className={cn("text-xs font-semibold", styles.text)}>{styles.label}</span>
      </span>

      <p className="text-[11px] leading-snug text-muted-foreground">{styles.meaning}</p>

      {hasFindings && (
        <div className="flex flex-wrap items-center gap-1">
          {failedChecks.map((check) => (
            <span
              key={`failed-${check}`}
              className="inline-flex items-center gap-1 rounded border border-destructive/25 bg-destructive/[0.07] px-1.5 py-0.5 text-[11px] font-medium text-destructive"
              title={`${formatCheckName(check)} — this check ran and did not pass.`}
            >
              <AlertTriangle size={11} strokeWidth={2.25} aria-hidden />
              {formatCheckName(check)}
            </span>
          ))}

          {/* Kept visually apart from the failures. A check that could not run
              is not a check that failed, and showing them alike would invent
              problems the engine never reported. */}
          {notAssessedChecks.map((check) => (
            <span
              key={`unrun-${check}`}
              className="inline-flex items-center gap-1 rounded border border-border bg-muted/30 px-1.5 py-0.5 text-[11px] text-muted-foreground"
              title={`${formatCheckName(check)} — could not be run on this capture, so it is neither a pass nor a failure.`}
            >
              {formatCheckName(check)}
              <span className="text-[10px]">(not run)</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

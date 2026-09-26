import React, { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  CircleDashed,
  Info,
  Loader2,
  ShieldCheck,
  Snowflake,
} from "lucide-react";
import type { BaselineHealth } from "@/types/baseline";
import {
  assessBaselineTrust,
  describeCoverage,
  describeSampleDepth,
  type BaselineTrust,
} from "@/lib/baseline-trust";
import { cn } from "@/lib/utils";

const TRUST_STYLES: Record<
  BaselineTrust,
  { box: string; text: string; Icon: typeof ShieldCheck; meaning: string }
> = {
  none: {
    box: "border-border bg-muted/30",
    text: "text-muted-foreground",
    Icon: CircleDashed,
    meaning:
      "Nothing is being compared against a learned normal for this sensor, so no reading can be called unusual yet.",
  },
  building: {
    box: "border-signal-light/40 bg-signal-light/10",
    text: "text-signal-dark",
    Icon: Loader2,
    meaning:
      "A baseline exists but has not been activated, so it is deliberately not used for comparison.",
  },
  weak: {
    box: "border-destructive/30 bg-destructive/[0.07]",
    text: "text-destructive",
    Icon: AlertTriangle,
    meaning:
      "Comparisons are running against this, but it rests on too little to carry a finding on its own.",
  },
  provisional: {
    box: "border-signal-light/40 bg-signal-light/10",
    text: "text-signal-dark",
    Icon: Info,
    meaning: "Usable, but read the caveats before drawing a conclusion from a small difference.",
  },
  sound: {
    box: "border-machine-healthy/30 bg-machine-healthy/10",
    text: "text-machine-healthy",
    Icon: ShieldCheck,
    meaning: "Enough data, recent enough, with nothing the engine wants to flag.",
  },
};

interface BaselineTrustBannerProps {
  health: BaselineHealth | undefined;
  isLoading: boolean;
  isError: boolean;
  className?: string;
}

/**
 * What the learned baseline for this sensor is currently worth.
 *
 * Sits above the list rather than on a row: the verdict is about the version in
 * force for the sensor, not about any one saved capture, and attaching it to a
 * row would claim something about that row it does not mean.
 */
export function BaselineTrustBanner({
  health,
  isLoading,
  isError,
  className,
}: BaselineTrustBannerProps) {
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-xl border border-border bg-muted/20 px-g4 py-g3",
          className
        )}
      >
        <Loader2 size={15} className="animate-spin text-muted-foreground" aria-hidden />
        <span className="text-sm text-muted-foreground">Checking baseline health…</span>
      </div>
    );
  }

  // A verdict that could not be fetched is reported as no verdict, never as a
  // good one. Same rule as everywhere else: absent is not a pass.
  const verdict = assessBaselineTrust(isError ? null : health);
  const styles = TRUST_STYLES[verdict.trust];
  const { Icon } = styles;

  const facts = health && health.available
    ? [describeSampleDepth(health), describeCoverage(health)].filter(
        (fact): fact is string => Boolean(fact)
      )
    : [];

  const version = health?.version;

  return (
    <div className={cn("rounded-xl border px-g4 py-g3", styles.box, className)}>
      <div className="flex flex-wrap items-start justify-between gap-g2">
        <div className="flex min-w-0 items-start gap-2">
          <Icon
            size={16}
            className={cn(styles.text, verdict.trust === "building" && "animate-spin")}
            strokeWidth={2.25}
            aria-hidden
          />
          <div className="min-w-0">
            <p className={cn("text-sm font-semibold", styles.text)}>
              {verdict.headline}
              {version && (
                <span className="ml-1.5 font-normal text-muted-foreground">
                  · v{version.version} ({version.state})
                </span>
              )}
              {version?.state === "frozen" && (
                <Snowflake
                  size={12}
                  className="ml-1 inline text-muted-foreground"
                  aria-label="frozen"
                />
              )}
            </p>
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{styles.meaning}</p>
          </div>
        </div>

        {verdict.reasons.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            className="inline-flex shrink-0 items-center gap-1 rounded border border-border bg-white/70 px-2 py-1 text-xs font-medium text-foreground hover:bg-white"
          >
            {verdict.reasons.length} caveat{verdict.reasons.length === 1 ? "" : "s"}
            <ChevronDown
              size={12}
              className={cn("transition-transform", expanded && "rotate-180")}
              aria-hidden
            />
          </button>
        )}
      </div>

      {facts.length > 0 && (
        <p className="mt-g2 text-xs text-muted-foreground">{facts.join(" · ")}</p>
      )}

      {expanded && verdict.reasons.length > 0 && (
        // The backend's own sentences, worst first, shown as written. They are
        // phrased to be acted on; paraphrasing them here would lose the numbers
        // that make them actionable.
        <ul className="mt-g2 space-y-1.5 border-t border-border/60 pt-g2">
          {verdict.reasons.map((reason) => (
            <li key={reason} className="flex gap-1.5 text-xs leading-snug text-muted-foreground">
              <span aria-hidden className="mt-1 h-1 w-1 shrink-0 rounded-full bg-current" />
              {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

import React, { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { Activity, BookOpen, Lightbulb, Sparkles, X } from "lucide-react";
import type { HealthMetricTrend } from "@/types/health-status";
import { buildMetricInsight, metricName } from "@/lib/metric-insight";
import { StatusBadge, StatusRail } from "@/components/ui/StatusBox";
import { STATUS_TONES } from "@/lib/status-box";
import { cn } from "@/lib/utils";

interface MetricInsightModalProps {
  open: boolean;
  metric: HealthMetricTrend;
  channelLabel: string;
  onClose: () => void;
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Activity;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-g2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-muted-foreground">
        <Icon size={13} aria-hidden />
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * The reading behind one metric card.
 *
 * Everything shown is computed in the browser from the segment values the card
 * already plots — see `buildMetricInsight`. It is stated plainly rather than
 * dressed up, and the caveats travel with it, because a confident paragraph
 * about one sub-second capture is exactly how a reading gets over-trusted.
 */
export function MetricInsightModal({
  open,
  metric,
  channelLabel,
  onClose,
}: MetricInsightModalProps) {
  // Only analysed while the panel is actually open. Every card in the grid
  // mounts one of these, so computing all ten readings on every render of the
  // section was work nobody had asked for.
  const insight = useMemo(
    () => (open ? buildMetricInsight(metric, channelLabel) : null),
    [open, metric, channelLabel]
  );

  // Escape closes, like every other dismissible layer in the app.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !insight) return null;

  const title = metricName(metric);
  const tone = STATUS_TONES[insight.tone];

  // Rendered into <body>, not where it sits in the tree.
  //
  // Its home is a metric card inside `.content-card`, which is `overflow:
  // hidden`, and whose hover rule applies `transform: translateY(-2px)`. A
  // transformed ancestor becomes the containing block for `position: fixed`,
  // so inline this overlay stops covering the viewport and gets clipped to the
  // card it came from. GraphWorkspace portals its own fullscreen shell for the
  // same reason.
  return createPortal(
    <div
      className="fixed inset-0 z-50 m-0 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-8"
      role="dialog"
      aria-modal="true"
      aria-labelledby="metric-insight-title"
      onClick={onClose}
    >
      <div
        className={cn(
          "relative w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-white shadow-xl",
          tone.wash
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <StatusRail tone={insight.tone} className="w-[4px]" />

        <div className="card-pad">
          <div className="mb-g3 flex items-start justify-between gap-g3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-signal-dark">
                <Sparkles size={13} aria-hidden />
                AI reading
              </p>
              <h2
                id="metric-insight-title"
                className="mt-1 truncate text-lg font-bold text-foreground"
              >
                {title}
                {metric.unit && (
                  <span className="ml-1.5 text-sm font-medium text-muted-foreground">
                    ({metric.unit})
                  </span>
                )}
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{channelLabel}</p>
            </div>
            <div className="flex shrink-0 items-center gap-g2">
              <StatusBadge tone={insight.tone}>{metric.status}</StatusBadge>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-warm hover:text-foreground"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <p className="rounded-lg border border-border bg-white px-g3 py-g2 text-sm font-semibold leading-relaxed text-foreground">
            {insight.headline}
          </p>

          <div className="mt-g4 space-y-g4">
            {insight.stats.length > 0 && (
              <div className="grid grid-cols-2 gap-g2 sm:grid-cols-3">
                {insight.stats.map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-md border border-border bg-white px-g2 py-1.5"
                  >
                    <p className="text-[10px] font-bold uppercase leading-none tracking-wide text-muted-foreground">
                      {stat.label}
                    </p>
                    <p className="mt-1 text-sm font-bold leading-tight text-foreground tabular-nums">
                      {stat.value}
                    </p>
                    {stat.hint && (
                      <p className="text-[10px] leading-tight text-muted-foreground">{stat.hint}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            <Section icon={Activity} title="What the graph is doing">
              <p className="text-sm leading-relaxed text-foreground">{insight.behaviour}</p>
            </Section>

            <Section icon={BookOpen} title="What this measures">
              <p className="text-sm leading-relaxed text-foreground">{insight.meaning}</p>
            </Section>

            {insight.suggestions.length > 0 && (
              <Section icon={Lightbulb} title="Suggested next steps">
                <ol className="space-y-g2">
                  {insight.suggestions.map((line, index) => (
                    <li
                      key={index}
                      className="flex gap-g2 rounded-r-md border border-border border-l-2 border-l-signal-light bg-warm px-g3 py-g2 text-sm leading-relaxed text-foreground"
                    >
                      <span className="shrink-0 font-bold text-signal-dark">{index + 1}.</span>
                      {line}
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            <div className="rounded-md border border-border bg-warm/60 px-g3 py-g2">
              {insight.caveats.map((line, index) => (
                <p key={index} className="text-xs leading-snug text-muted-foreground">
                  {line}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

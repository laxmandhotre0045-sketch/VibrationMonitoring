import { AlertTriangle, CheckCircle2, Clock, Database } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { cardPad } from "@/lib/layout";
import { cn } from "@/lib/utils";
import type { CaptureHistory } from "@/types/dashboard";

/**
 * MOM item 10 — the dates of data entries, and when the last one arrived.
 *
 * The question this card exists to answer is not "what is the timestamp of the
 * newest row" but "is the feed alive". Those differ: a date on its own reads as
 * current no matter how old it is, because a reader has to do the subtraction
 * to notice. So the age leads, and the timestamp supports it.
 *
 * The age comes from the server. A browser computing it from its own clock
 * reports clock skew as data age, and on a plant PC that is off by ten minutes
 * the card would accuse a healthy feed of being stale.
 */

/** Captures arrive on the collection interval — two minutes here. These bands
 *  are multiples of that, so "late" means several intervals were missed rather
 *  than one arriving a little behind. */
const STALE_AFTER_S = 15 * 60;
const DEAD_AFTER_S = 60 * 60;

function describeAge(seconds: number | null): string {
  if (seconds === null) return "unknown";
  if (seconds < 90) return `${Math.round(seconds)} seconds ago`;
  const minutes = seconds / 60;
  if (minutes < 90) return `${Math.round(minutes)} minutes ago`;
  const hours = minutes / 60;
  if (hours < 36) return `${hours.toFixed(1)} hours ago`;
  return `${Math.round(hours / 24)} days ago`;
}

function freshness(seconds: number | null) {
  if (seconds === null) {
    return { tone: "unknown", label: "No data", Icon: AlertTriangle,
             text: "text-muted-foreground", ring: "border-border" };
  }
  if (seconds > DEAD_AFTER_S) {
    return { tone: "dead", label: "Feed stopped", Icon: AlertTriangle,
             text: "text-machine-critical", ring: "border-machine-critical/40" };
  }
  if (seconds > STALE_AFTER_S) {
    return { tone: "stale", label: "Running late", Icon: Clock,
             text: "text-machine-warning", ring: "border-machine-warning/40" };
  }
  return { tone: "live", label: "Live", Icon: CheckCircle2,
           text: "text-machine-healthy", ring: "border-machine-healthy/30" };
}

export function DataFreshnessCard({ history }: { history?: CaptureHistory }) {
  const last = history?.last_entry ?? null;
  const state = freshness(last?.age_seconds ?? null);
  const { Icon } = state;

  return (
    <GlassCard className={cardPad} equalHeight>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">Latest data entry</p>
          <p className={cn("mt-2 text-2xl font-semibold tabular-nums", state.text)}>
            {last ? describeAge(last.age_seconds) : "No captures yet"}
          </p>
          {last && (
            <p className="mt-1 text-sm text-foreground">
              {new Date(last.at).toLocaleString()}
            </p>
          )}
        </div>
        <span
          className={cn(
            "flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
            state.ring, state.text,
          )}
        >
          <Icon size={13} />
          {state.label}
        </span>
      </div>

      {last ? (
        <dl className="mt-4 space-y-1.5 border-t border-border pt-3 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Machine</dt>
            <dd className="truncate text-foreground">{last.machine_name}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Sensor</dt>
            <dd className="truncate text-foreground">{last.sensor_location}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Capture</dt>
            <dd className="tabular-nums text-foreground">
              {last.sample_count.toLocaleString()} × {last.channel_count} ch @{" "}
              {(last.sample_rate_hz / 1000).toFixed(1)} kSPS
            </dd>
          </div>
          {history && history.entries_by_date.length > 0 && (
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Days with data</dt>
              <dd className="tabular-nums text-foreground">
                {history.entries_by_date.length}
              </dd>
            </div>
          )}
        </dl>
      ) : (
        <p className="mt-4 border-t border-border pt-3 text-sm text-muted-foreground">
          Nothing has been ingested for this sensor yet.
        </p>
      )}

      {history && history.entries_by_date.length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted-foreground">
            <Database size={12} /> Entry dates
          </p>
          <ul className="space-y-1 text-sm">
            {/* Only days that actually have data are returned, so a gap in this
                list is a real gap in monitoring rather than a rendering choice. */}
            {history.entries_by_date.slice(0, 5).map((d) => (
              <li key={d.date} className="flex justify-between gap-3 tabular-nums">
                <span className="text-foreground">{d.date}</span>
                <span className="text-muted-foreground">
                  {d.count} {d.count === 1 ? "capture" : "captures"}
                  <span className="ml-2 text-muted-foreground">
                    {d.first_at.slice(11, 16)}–{d.last_at.slice(11, 16)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {history.entries_by_date.length > 5 && (
            <p className="mt-2 text-xs text-muted-foreground">
              +{history.entries_by_date.length - 5} earlier{" "}
              {history.entries_by_date.length - 5 === 1 ? "day" : "days"}
            </p>
          )}
        </div>
      )}
    </GlassCard>
  );
}

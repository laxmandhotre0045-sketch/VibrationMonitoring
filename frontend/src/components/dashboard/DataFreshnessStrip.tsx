import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ChevronRight, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CaptureHistory } from "@/types/dashboard";

/**
 * One line on the dashboard saying whether the feed is alive.
 *
 * The detail behind it — per-channel levels, window coverage, entry dates —
 * lives on Sensor Data. It belongs there rather than here: it is reference
 * material someone consults when a number looks wrong, not something to re-read
 * on every visit. What does belong on every visit is the single fact that
 * qualifies everything below it, which is whether the data is current, and that
 * fits in a line.
 *
 * Age rather than timestamp: a date reads as current however old it is, because
 * noticing requires the reader to do the subtraction.
 */

//: Multiples of the collection interval, so "late" means several captures were
//: missed rather than one arriving slightly behind.
const STALE_AFTER_S = 15 * 60;
const DEAD_AFTER_S = 60 * 60;

function describeAge(seconds: number | null): string {
  if (seconds === null) return "unknown";
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  const minutes = seconds / 60;
  if (minutes < 90) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 36) return `${hours.toFixed(1)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function DataFreshnessStrip({ history }: { history?: CaptureHistory }) {
  const last = history?.last_entry ?? null;
  const age = last?.age_seconds ?? null;

  const state =
    age === null
      ? { Icon: AlertTriangle, cls: "text-machine-offline", label: "No data" }
      : age > DEAD_AFTER_S
        ? { Icon: AlertTriangle, cls: "text-machine-critical", label: "Feed stopped" }
        : age > STALE_AFTER_S
          ? { Icon: Clock, cls: "text-machine-warning", label: "Running late" }
          : { Icon: CheckCircle2, cls: "text-machine-healthy", label: "Live" };
  const { Icon } = state;
  const todays = history?.entries_by_date?.[0];

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-white px-3 py-2 text-sm">
      <span className={cn("flex items-center gap-1.5 font-medium", state.cls)}>
        <Icon size={14} />
        {state.label}
      </span>

      {last ? (
        <>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">
            Last data <span className="tabular-nums">{describeAge(age)}</span>
          </span>
          <span className="hidden text-muted-foreground sm:inline">·</span>
          <span className="hidden truncate text-muted-foreground sm:inline">
            {last.machine_name}
          </span>
          {todays && (
            <>
              <span className="hidden text-muted-foreground md:inline">·</span>
              <span className="hidden tabular-nums text-muted-foreground md:inline">
                {todays.count} today
              </span>
            </>
          )}
        </>
      ) : (
        <span className="text-muted-foreground">Nothing ingested yet</span>
      )}

      <Link
        to="/sensor-data"
        className="ml-auto flex items-center gap-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        History
        <ChevronRight size={13} />
      </Link>
    </div>
  );
}

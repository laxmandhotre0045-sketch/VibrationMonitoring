import { ArrowDownRight, ArrowRight, ArrowUpRight, Info, Minus } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { cardPad } from "@/lib/layout";
import { cn } from "@/lib/utils";
import type { ChannelTrend, WindowSummary } from "@/types/dashboard";

/**
 * MOM item 12 — 7-day and 30-day summary cards.
 *
 * The design problem here is not the layout, it is honesty about partial data.
 * "7 days · 26 captures" is true and misleading: those captures might span a
 * week or forty minutes, and nothing on the card tells the reader which. So the
 * coverage bar is not decoration — it is the part that stops the heading being
 * read as a promise about the whole window.
 *
 * Trends are withheld rather than estimated. The backend returns `trend: null`
 * with a reason whenever the data underneath could not support the claim, and
 * this card shows that reason instead of an arrow. An arrow drawn through forty
 * minutes is not a weekly trend; it is noise pointing somewhere.
 */

function TrendBadge({ channel }: { channel: ChannelTrend }) {
  if (channel.trend === null) {
    return (
      <span className="text-xs text-muted-foreground" title={channel.trend_blocked_reason ?? ""}>
        —
      </span>
    );
  }
  const pct = channel.trend * 100;
  const map = {
    rising: { Icon: ArrowUpRight, cls: "text-machine-warning" },
    falling: { Icon: ArrowDownRight, cls: "text-signal-dark" },
    flat: { Icon: Minus, cls: "text-muted-foreground" },
    unknown: { Icon: ArrowRight, cls: "text-muted-foreground" },
  } as const;
  const { Icon, cls } = map[channel.direction] ?? map.unknown;
  return (
    <span className={cn("flex items-center justify-end gap-1 text-xs tabular-nums", cls)}>
      <Icon size={12} />
      {pct > 0 ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

export function WindowSummaryCard({ window }: { window: WindowSummary }) {
  const coveragePct = window.coverage_fraction * 100;
  // Below half the window, the figures describe a sample of it rather than the
  // window itself, and the card says so rather than letting the title imply
  // otherwise.
  const partial = window.coverage_fraction < 0.5;
  const blockedReason = window.channels.find((c) => c.trend_blocked_reason)?.trend_blocked_reason;

  return (
    <GlassCard className={cardPad} equalHeight>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-foreground">Last {window.days} days</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {window.captures} {window.captures === 1 ? "capture" : "captures"}
        </span>
      </div>

      {window.captures === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {window.note ?? `No captures in the last ${window.days} days.`}
        </p>
      ) : (
        <>
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Window coverage</span>
              <span className="tabular-nums">
                {coveragePct < 1 ? coveragePct.toFixed(2) : coveragePct.toFixed(0)}%
              </span>
            </div>
            <div
              className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`Data covers ${coveragePct.toFixed(1)} percent of the ${window.days} day window`}
            >
              <div
                className={cn("h-full rounded-full", partial ? "bg-machine-warning" : "bg-machine-healthy")}
                /* Floored at 1% so a real but tiny coverage is still visible;
                   a bar of literally zero width reads as "no data", which is a
                   different and wrong message. */
                style={{ width: `${Math.max(coveragePct, 1)}%` }}
              />
            </div>
            <p className="mt-1.5 text-xs tabular-nums text-muted-foreground">
              {window.active_days} {window.active_days === 1 ? "day" : "days"} with data ·{" "}
              {window.span_hours < 1
                ? `${(window.span_hours * 60).toFixed(0)} min span`
                : `${window.span_hours.toFixed(1)} h span`}
            </p>
          </div>

          {window.note && (
            <p className="mt-3 flex gap-1.5 rounded border border-machine-warning/30 bg-machine-warning/5 p-2 text-xs text-foreground">
              <Info size={13} className="mt-0.5 shrink-0" />
              <span>{window.note}</span>
            </p>
          )}

          <div className="mt-3 border-t border-border pt-3">
            <div className="mb-1.5 flex justify-between text-xs uppercase tracking-wider text-muted-foreground">
              <span>Channel</span>
              <span className="flex gap-4">
                <span>Mean AC&nbsp;RMS&nbsp;(g)</span>
                <span className="w-14 text-right">Trend</span>
              </span>
            </div>
            <ul className="space-y-1">
              {window.channels.map((c) => (
                <li key={c.channel_index} className="flex justify-between gap-3 text-sm">
                  <span className="text-foreground">ch{c.channel_index}</span>
                  <span className="flex items-center gap-4">
                    <span className="tabular-nums text-foreground">{c.rms_mean.toFixed(5)}</span>
                    <span className="w-14 text-right">
                      <TrendBadge channel={c} />
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {blockedReason && (
              <p className="mt-2 text-xs text-muted-foreground">
                Trends withheld: {blockedReason}
              </p>
            )}
          </div>
        </>
      )}
    </GlassCard>
  );
}

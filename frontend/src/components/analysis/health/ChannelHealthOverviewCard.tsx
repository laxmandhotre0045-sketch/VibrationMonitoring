import React from "react";
import { Activity } from "lucide-react";
import type { ChannelHealthOverviewData } from "@/types/features";
import { cn } from "@/lib/utils";

interface ChannelHealthOverviewCardProps {
  data: ChannelHealthOverviewData;
  channelLabel: string;
  className?: string;
}

function formatComputedAt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function ChannelHealthOverviewCard({
  data,
  channelLabel,
  className,
}: ChannelHealthOverviewCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border border-l-2 border-l-signal-light bg-white card-pad",
        "shadow-sm",
        className
      )}
    >
      <div className="flex items-center gap-2 mb-g3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#FFA500]/10 text-[#FFA500]">
          <Activity size={20} aria-hidden />
        </span>
        <div>
          <h3 className="text-sm font-bold text-foreground">Channel Health Overview</h3>
          <p className="text-xs text-muted-foreground">{channelLabel}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <OverviewItem label="Health State" value={data.health_state} emphasize />
        <OverviewItem label="Feature Count" value={String(data.feature_count)} />
        <OverviewItem
          label="Last Computed"
          value={formatComputedAt(data.computed_at)}
        />
        <OverviewItem
          label="Baseline Used"
          value={data.baseline_name ?? "No baseline selected"}
        />
      </div>
    </div>
  );
}

function OverviewItem({
  label,
  value,
  emphasize = false,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface/40 px-3 py-2.5 min-h-[72px]">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={cn(
          "mt-g1 text-sm leading-snug",
          emphasize ? "font-bold text-brand" : "font-semibold text-foreground"
        )}
      >
        {value}
      </p>
    </div>
  );
}

export function ChannelHealthOverviewSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-white card-pad min-h-[140px] animate-pulse",
        className
      )}
    >
      <div className="h-4 w-48 rounded bg-muted/60 mb-g3" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-lg bg-muted/40" />
        ))}
      </div>
    </div>
  );
}

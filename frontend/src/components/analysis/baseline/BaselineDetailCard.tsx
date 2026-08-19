import React from "react";
import type { Baseline } from "@/types/baseline";
import { BaselinePlotStatusBadge } from "./baseline-utils";
import { cn } from "@/lib/utils";

interface BaselineDetailCardProps {
  baseline: Baseline;
  formatDateTime: (iso: string) => string;
  className?: string;
}

export function BaselineDetailCard({
  baseline,
  formatDateTime,
  className,
}: BaselineDetailCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border border-l-2 border-l-signal-light bg-white px-g4 py-g3 shadow-sm",
        className
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Baseline Information
      </p>
      <h4 className="mt-2 text-base font-bold text-foreground">{baseline.name}</h4>
      <dl className="mt-g2 grid grid-cols-1 sm:grid-cols-2 gap-x-g3 gap-y-g1 text-sm">
        <div>
          <dt className="text-muted-foreground">Created</dt>
          <dd className="font-medium text-foreground">{formatDateTime(baseline.created_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Channels</dt>
          <dd className="font-medium text-foreground">{baseline.channel_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Samples</dt>
          <dd className="font-medium text-foreground">{baseline.sample_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Plot Status</dt>
          <dd className="mt-0.5">
            <BaselinePlotStatusBadge status={baseline.plots_status} />
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">Source Upload</dt>
          <dd className="font-medium text-foreground break-all">
            {baseline.original_filename || baseline.source_upload_id || "—"}
          </dd>
        </div>
      </dl>
    </div>
  );
}

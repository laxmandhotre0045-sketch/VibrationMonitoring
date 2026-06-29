import React from "react";
import { LayoutGrid } from "lucide-react";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import {
  channelLabel,
  getChannelReadinessStatus,
} from "@/lib/vibration-settings-utils";
import type { ChannelConfig, ChannelReadinessStatus } from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<
  ChannelReadinessStatus,
  { dot: string; badge: string; label: string }
> = {
  configured: {
    dot: "bg-machine-healthy",
    badge: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/25",
    label: "Configured",
  },
  partial: {
    dot: "bg-signal-light",
    badge: "bg-signal-light/15 text-signal-dark border-signal-light/40",
    label: "Partial",
  },
  empty: {
    dot: "bg-muted-foreground/40",
    badge: "bg-muted/50 text-muted-foreground border-border",
    label: "Not Configured",
  },
};

function formatAxis(axis: string): string {
  if (!axis) return "—";
  return axis.charAt(0).toUpperCase() + axis.slice(1);
}

function formatDataType(dataType: string): string {
  if (!dataType) return "—";
  return dataType.charAt(0).toUpperCase() + dataType.slice(1);
}

interface ChannelMappingOverviewProps {
  channels: ChannelConfig[];
}

export function ChannelMappingOverview({ channels }: ChannelMappingOverviewProps) {
  return (
    <SettingsSectionCard
      title="Channel Mapping Overview"
      description="Quick visual summary of channel configuration readiness."
      icon={<LayoutGrid size={22} strokeWidth={2} />}
    >
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Channel Mapping Severity
      </p>
      <div className="mb-4 flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-machine-healthy" />
          Fully Configured
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-signal-light" />
          Partially Configured
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
          Not Configured
        </span>
      </div>

      {channels.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No channel severity indicators — add channel rows to begin mapping.
        </p>
      ) : (
        <div
          className="grid gap-3"
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
          }}
        >
          {channels.map((channel) => {
            const status = getChannelReadinessStatus(channel);
            const styles = STATUS_STYLES[status];

            return (
              <div
                key={channel.channelNo}
                className={cn(
                  "rounded-lg border px-3 py-3 transition-all duration-200",
                  "hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(21,54,109,0.08)]",
                  styles.badge
                )}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-sm font-bold">{channelLabel(channel.channelNo)}</span>
                  <span className={cn("h-2 w-2 rounded-full shrink-0", styles.dot)} />
                </div>
                <p className="text-xs font-semibold leading-snug">{formatAxis(channel.axis)}</p>
                <p className="text-xs leading-snug mt-0.5 opacity-90">
                  {formatDataType(channel.dataType)}
                </p>
                {channel.measurementPointName && (
                  <p
                    className="text-[11px] mt-1.5 truncate opacity-80"
                    title={channel.measurementPointName}
                  >
                    {channel.measurementPointName}
                  </p>
                )}
                <p className="text-[10px] font-semibold uppercase tracking-wide mt-2 opacity-75">
                  {styles.label}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </SettingsSectionCard>
  );
}

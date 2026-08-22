import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { FeatureStatusItem } from "@/types/features";
import {
  formatFeatureUnit,
  formatFeatureValue,
  groupFeatureStatusItems,
} from "@/lib/feature-display";
import { FeatureStatusBadge } from "./FeatureStatusBadge";
import { cn } from "@/lib/utils";

interface FeatureStatusTableProps {
  items: FeatureStatusItem[];
  className?: string;
}

function statusRowClass(status: FeatureStatusItem["status"]): string {
  if (status === "critical") return "bg-destructive/5";
  if (status === "warning") return "bg-signal-light/10";
  return "";
}

function FeatureTableBody({ items }: { items: FeatureStatusItem[] }) {
  return (
    <tbody>
      {items.map((item) => (
        <tr
          key={item.feature_key ?? item.feature}
          className={cn(
            "border-b border-border last:border-b-0 hover:bg-warm/40 transition-colors",
            statusRowClass(item.status)
          )}
        >
          <td className="px-3 py-2.5 font-medium text-foreground">{item.feature}</td>
          <td className="px-3 py-2.5 font-semibold text-foreground">
            {formatFeatureValue(item.value)}
          </td>
          <td className="px-3 py-2.5 text-muted-foreground">
            {formatFeatureUnit(item.unit)}
          </td>
          <td className="px-3 py-2.5">
            <FeatureStatusBadge status={item.status} />
          </td>
        </tr>
      ))}
    </tbody>
  );
}

function FeatureCategorySection({
  title,
  items,
  defaultOpen = true,
}: {
  title: string;
  items: FeatureStatusItem[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 bg-surface/60 px-3 py-2.5 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
          {title}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-3 py-2 font-semibold text-muted-foreground">Feature</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Value</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Unit</th>
              <th className="px-3 py-2 font-semibold text-muted-foreground">Status</th>
            </tr>
          </thead>
          <FeatureTableBody items={items} />
        </table>
      )}
    </div>
  );
}

export function FeatureStatusTable({ items, className }: FeatureStatusTableProps) {
  const groups = groupFeatureStatusItems(items);
  if (groups.length === 0) return null;

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-xl border border-border border-l-2 border-l-signal-light shadow-sm",
        className
      )}
    >
      {groups.map((group) => (
        <FeatureCategorySection
          key={group.category}
          title={group.label}
          items={group.items}
        />
      ))}
    </div>
  );
}

export function FeatureStatusTableSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border bg-white p-3 space-y-g2 animate-pulse", className)}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-9 rounded-md bg-muted/40" />
      ))}
    </div>
  );
}

import { formatDistanceToNow } from "date-fns";
import type { EquipmentHealthStatus } from "@/types/dashboard";

export const STATUS_META: Record<
  EquipmentHealthStatus,
  { label: string; dot: string; box: string; text: string }
> = {
  critical: {
    label: "Critical",
    dot: "bg-machine-critical",
    box: "border-machine-critical/30 bg-machine-critical/5",
    text: "text-machine-critical",
  },
  warning: {
    label: "Warning",
    dot: "bg-machine-warning",
    box: "border-machine-warning/30 bg-machine-warning/5",
    text: "text-machine-warning",
  },
  normal: {
    label: "Healthy",
    dot: "bg-machine-healthy",
    box: "border-machine-healthy/30 bg-machine-healthy/5",
    text: "text-machine-healthy",
  },
  no_baseline: {
    label: "No Baseline",
    dot: "bg-machine-offline",
    box: "border-border bg-muted/20",
    text: "text-muted-foreground",
  },
  no_data: {
    label: "No Data",
    dot: "bg-machine-offline",
    box: "border-border bg-muted/20",
    text: "text-muted-foreground",
  },
};

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return "—";
  }
}

import React from "react";
import type { HealthStatusLevel, HealthThresholdRow } from "@/types/health-status";
import { cn } from "@/lib/utils";

const STATUS_CELL: Record<HealthStatusLevel, string> = {
  healthy: "text-machine-healthy",
  warning: "text-signal-dark",
  danger: "text-destructive",
  neutral: "text-muted-foreground",
};

const STATUS_LABEL: Record<HealthStatusLevel, string> = {
  healthy: "OK",
  warning: "Caution",
  danger: "Warning",
  neutral: "",
};

interface HealthThresholdsTableProps {
  rows: HealthThresholdRow[];
  className?: string;
}

export function HealthThresholdsTable({ rows, className }: HealthThresholdsTableProps) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No health parameters available for the selected channel.
      </p>
    );
  }

  return (
    <div className={cn("overflow-x-auto rounded-md border border-border border-l-2 border-l-signal-light", className)}>
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-border bg-surface/60 text-left">
            <th className="px-3 py-2 font-semibold text-muted-foreground">Parameter</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Latest</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Delta vs Prior</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Range (Period)</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Caution Limit</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Warning Limit</th>
            <th className="px-3 py-2 font-semibold text-muted-foreground">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.parameter} className="border-b border-border last:border-b-0">
              <td className="px-3 py-2 font-medium text-foreground">{row.parameter}</td>
              <td className="px-3 py-2 text-foreground">{row.latest}</td>
              <td className="px-3 py-2 text-foreground">{row.deltaVsPrior}</td>
              <td className="px-3 py-2 text-foreground">{row.rangePeriod}</td>
              <td className="px-3 py-2 text-foreground">{row.cautionLimit}</td>
              <td className="px-3 py-2 text-foreground">{row.warningLimit}</td>
              <td className={cn("px-3 py-2 font-semibold", STATUS_CELL[row.status])}>
                {STATUS_LABEL[row.status]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

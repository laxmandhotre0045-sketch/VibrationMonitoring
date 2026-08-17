import React, { useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, ShieldCheck } from "lucide-react";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { STATUS_META, relativeTime } from "@/lib/alert-status";
import type { EquipmentHealthStatus } from "@/types/dashboard";
import { cn } from "@/lib/utils";

interface NotificationBellProps {
  className?: string;
}

export function NotificationBell({ className }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, dataUpdatedAt } = useDashboardSummary();

  const alerts = data?.alerts ?? [];
  const count = alerts.length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-label={count > 0 ? `Notifications, ${count} active alerts` : "Notifications"}
        className={cn("relative p-2", className)}
      >
        <Bell size={18} className="text-brand" />
        {count > 0 && (
          <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 flex items-center justify-center text-[10px] font-bold text-white bg-signal-dark rounded-full">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-1 w-[340px] z-20 rounded-lg bg-white border border-border shadow-card-hover"
            >
              <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-border">
                <p className="text-sm font-semibold text-brand">Notifications</p>
                <span className="text-xs text-muted-foreground">
                  {isLoading
                    ? "Loading…"
                    : isError
                      ? "Unavailable"
                      : `Updated ${relativeTime(new Date(dataUpdatedAt).toISOString())}`}
                </span>
              </div>

              <div className="max-h-[380px] overflow-y-auto">
                {isError ? (
                  <p className="px-4 py-6 text-sm text-muted-foreground text-center">
                    Could not load alerts.
                  </p>
                ) : count === 0 ? (
                  <div className="px-4 py-8 flex flex-col items-center gap-2 text-center">
                    <ShieldCheck size={22} className="text-machine-healthy" />
                    <p className="text-sm text-muted-foreground">
                      No active alerts — fleet is within normal thresholds.
                    </p>
                  </div>
                ) : (
                  <div className="p-2 space-y-2">
                    {alerts.map((alert, i) => {
                      const meta =
                        STATUS_META[alert.status as EquipmentHealthStatus] ?? STATUS_META.no_baseline;
                      return (
                        <Link
                          key={`${alert.equipment_id}-${alert.channel}-${alert.feature_code}-${i}`}
                          to={`/equipment/${alert.equipment_id}/edit`}
                          onClick={() => setOpen(false)}
                          className={cn(
                            "block rounded-lg border px-3 py-2.5 transition-colors hover:brightness-95",
                            meta.box
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <p className="font-semibold text-brand text-sm truncate">
                              {alert.machine_name}
                            </p>
                            <span className={cn("text-xs font-semibold shrink-0", meta.text)}>
                              {meta.label}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {alert.feature_name ?? alert.feature_code} · CH-{alert.channel + 1} ·{" "}
                            {alert.value.toFixed(2)} {alert.unit}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {relativeTime(alert.computed_at)}
                          </p>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

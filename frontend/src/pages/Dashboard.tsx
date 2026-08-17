import React from "react";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Cpu,
  Gauge,
  Radio,
  ShieldCheck,
} from "lucide-react";
import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { IndustrialEmptyState } from "@/components/equipment/industrial/IndustrialEmptyState";
import { cardSizing } from "@/lib/card-sizing";
import { cn } from "@/lib/utils";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import type { EquipmentHealthStatus } from "@/types/dashboard";

const STATUS_META: Record<
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

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return "—";
  }
}

export function Dashboard() {
  const { data, isLoading, isError } = useDashboardSummary();

  const counts = data?.counts;
  const hasFleet = (counts?.total ?? 0) > 0;

  const kpis = [
    {
      label: "Fleet Health",
      value: counts?.average_health_score != null ? `${counts.average_health_score}%` : "—",
      icon: Gauge,
      text: "text-brand",
    },
    {
      label: "Critical",
      value: counts ? counts.critical : "—",
      icon: AlertTriangle,
      text: "text-machine-critical",
    },
    {
      label: "Warning",
      value: counts ? counts.warning : "—",
      icon: Activity,
      text: "text-machine-warning",
    },
    {
      label: "Healthy",
      value: counts ? counts.normal : "—",
      icon: ShieldCheck,
      text: "text-machine-healthy",
    },
  ];

  return (
    <div className="space-y-6">
      <PageHero
        title="Operations Dashboard"
        subtitle="Real-time fleet health, vibration insights, and predictive analytics across your industrial asset portfolio."
        breadcrumbs={[{ label: "Home", href: "/" }, { label: "Operations Dashboard" }]}
        equipmentCount={counts?.total}
      />

      {isError && (
        <IndustrialEmptyState message="Couldn't load fleet dashboard data. Check that the backend is reachable and try again." />
      )}

      <div>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-bold text-brand tracking-tight">Fleet Overview</h2>
        </div>
        <div className="h-0.5 w-10 bg-brand-accent rounded-full mb-4" />
        <div className={cn("grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4", cardSizing.gridEqual)}>
          {kpis.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <GlassCard key={stat.label} equalHeight delay={0.05 + i * 0.05} className="p-5">
                <div className={cn(cardSizing.kpiBody, "gap-4")}>
                  <div className="w-9 h-9 rounded-lg bg-white border border-border flex items-center justify-center shrink-0">
                    <Icon size={18} className={stat.text} />
                  </div>
                  <div className="min-w-0">
                    <p className={cn("text-kpi-value mb-0.5", isLoading && "opacity-40")}>{stat.value}</p>
                    <p className="text-base font-medium text-muted-foreground">{stat.label}</p>
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      </div>

      {!isLoading && !hasFleet ? (
        <GlassCard className="p-5" delay={0.3}>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="text-card-title text-brand">Start with Equipment Master Data</h3>
              <p className="text-helper mt-1">
                Register your assets to enable vibration intelligence and predictive maintenance.
              </p>
            </div>
            <Link to="/equipment">
              <Button icon={<ArrowRight size={16} />}>Open Equipment Master</Button>
            </Link>
          </div>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <GlassCard className="p-5 lg:col-span-2" delay={0.3}>
            <div className="flex items-center gap-2 mb-4">
              <Cpu size={16} className="text-brand" />
              <h3 className="text-card-title text-brand">Fleet Health Status</h3>
            </div>
            {data && data.equipment_health.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {data.equipment_health.map((eq) => {
                  const meta = STATUS_META[eq.status];
                  return (
                    <Link
                      key={eq.equipment_id}
                      to={`/equipment/${eq.equipment_id}/edit`}
                      className={cn(
                        "rounded-lg border px-4 py-3 transition-all hover:-translate-y-0.5 hover:shadow-md",
                        meta.box
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-brand truncate">{eq.machine_name}</p>
                        <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", meta.dot)} />
                      </div>
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {eq.plant_name} · {eq.area}
                      </p>
                      <div className="flex items-center justify-between mt-2">
                        <span className={cn("text-xs font-semibold", meta.text)}>{meta.label}</span>
                        <span className="text-xs text-muted-foreground">{relativeTime(eq.last_upload_at)}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <IndustrialEmptyState message="Loading fleet health data…" />
            )}
          </GlassCard>

          <GlassCard className="p-5" delay={0.35}>
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={16} className="text-machine-warning" />
              <h3 className="text-card-title text-brand">Maintenance Alerts</h3>
            </div>
            {data && data.alerts.length > 0 ? (
              <div className="space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
                {data.alerts.map((alert, i) => {
                  const meta = STATUS_META[alert.status as EquipmentHealthStatus] ?? STATUS_META.no_baseline;
                  return (
                    <div
                      key={`${alert.equipment_id}-${alert.channel}-${alert.feature_code}-${i}`}
                      className={cn("rounded-lg border px-3 py-2.5", meta.box)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-brand text-sm truncate">{alert.machine_name}</p>
                        <span className={cn("text-xs font-semibold shrink-0", meta.text)}>{meta.label}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {alert.feature_name ?? alert.feature_code} · CH-{alert.channel + 1} ·{" "}
                        {alert.value.toFixed(2)} {alert.unit}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">{relativeTime(alert.computed_at)}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <IndustrialEmptyState message="No active alerts — fleet is within normal thresholds." />
            )}
          </GlassCard>
        </div>
      )}

      {hasFleet && (
        <GlassCard className="p-5" delay={0.4}>
          <div className="flex items-center gap-2 mb-4">
            <Radio size={16} className="text-signal-dark" />
            <h3 className="text-card-title text-brand">Signal Analytics Feed</h3>
          </div>
          {data && data.recent_activity.length > 0 ? (
            <div className="space-y-2">
              {data.recent_activity.map((activity) => (
                <div
                  key={activity.upload_id}
                  className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-warm border border-border"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-brand truncate">{activity.machine_name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {activity.mounting_location} · {activity.original_filename ?? "manual capture"}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs font-medium text-muted-foreground capitalize">
                      {activity.features_status}
                    </span>
                    <span className="text-xs text-muted-foreground">{relativeTime(activity.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <IndustrialEmptyState message="No signal uploads yet. Upload sensor data from Equipment Master to see activity here." />
          )}
        </GlassCard>
      )}
    </div>
  );
}

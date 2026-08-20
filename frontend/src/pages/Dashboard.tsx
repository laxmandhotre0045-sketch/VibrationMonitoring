import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { PageSection } from "@/components/layout/PageSection";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { IndustrialEmptyState } from "@/components/equipment/industrial/IndustrialEmptyState";
import { PanelPagination } from "@/components/ui/PanelPagination";
import { cardSizing } from "@/lib/card-sizing";
import { cardPad, gridGolden, gridMetrics, pageStack } from "@/lib/layout";
import { cn } from "@/lib/utils";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { STATUS_META, relativeTime } from "@/lib/alert-status";
import type { EquipmentHealthStatus } from "@/types/dashboard";

export function Dashboard() {
  const { data, isLoading, isError } = useDashboardSummary();

  const counts = data?.counts;
  const hasFleet = (counts?.total ?? 0) > 0;

  const fleet = data?.equipment_health ?? [];
  const alerts = data?.alerts ?? [];

  // The two panels share a `grid-golden` row, but the backend caps alerts at 20
  // while fleet health is unbounded. One column of 20 alerts made the row far
  // taller than the fleet grid needed, leaving dead space under it. Page the
  // alerts at one row per fleet row so both panels end level. The fleet grid is
  // 2-up from Tailwind's `sm`, 1-up below it.
  const fleetIsTwoUp = useMediaQuery("(min-width: 640px)");
  const fleetRows = Math.ceil(fleet.length / (fleetIsTwoUp ? 2 : 1));
  // When a pager shows it occupies a row of its own, so the list gives one back.
  // Fits-on-one-page stays at the full count and renders no pager at all, which
  // keeps this stable rather than oscillating between the two sizes.
  const alertsPerPage = Math.max(3, alerts.length > fleetRows ? fleetRows - 1 : fleetRows);
  const alertPageCount = Math.max(1, Math.ceil(alerts.length / alertsPerPage));

  const [alertPage, setAlertPage] = useState(1);
  useEffect(() => {
    // Page size follows the viewport and the fleet size, so the current page can
    // fall off the end without the user touching anything.
    if (alertPage > alertPageCount) setAlertPage(alertPageCount);
  }, [alertPage, alertPageCount]);

  const alertOffset = (alertPage - 1) * alertsPerPage;
  const visibleAlerts = alerts.slice(alertOffset, alertOffset + alertsPerPage);

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
    <div className={pageStack}>
      <PageHero
        title="Operations Dashboard"
        subtitle="Real-time fleet health, vibration insights, and predictive analytics across your industrial asset portfolio."
        breadcrumbs={[{ label: "Home", href: "/" }, { label: "Operations Dashboard" }]}
        equipmentCount={counts?.total}
      />

      {isError && (
        <IndustrialEmptyState message="Couldn't load fleet dashboard data. Check that the backend is reachable and try again." />
      )}

      <PageSection title="Fleet Overview">
        <div className={gridMetrics}>
          {kpis.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <GlassCard key={stat.label} equalHeight delay={0.05 + i * 0.05} className={cardPad}>
                <div className={cn(cardSizing.kpiBody, "gap-g3")}>
                  <div className="w-9 h-9 rounded-lg bg-white border border-border flex items-center justify-center shrink-0">
                    <Icon size={18} className={stat.text} />
                  </div>
                  <div className="min-w-0">
                    <p className={cn("text-kpi-value", isLoading && "opacity-40")}>{stat.value}</p>
                    <p className="text-sm font-medium text-muted-foreground mt-g1">{stat.label}</p>
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      </PageSection>

      {!isLoading && !hasFleet ? (
        <GlassCard className={cardPad} delay={0.3}>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-g3">
            <div>
              <h3 className="text-card-title text-brand">Start with Equipment Master Data</h3>
              <p className="text-helper mt-g1">
                Register your assets to enable vibration intelligence and predictive maintenance.
              </p>
            </div>
            <Link to="/equipment">
              <Button icon={<ArrowRight size={16} />}>Open Equipment Master</Button>
            </Link>
          </div>
        </GlassCard>
      ) : (
        <div className={gridGolden}>
          <GlassCard equalHeight className={cardPad} delay={0.3}>
            <div className="flex items-center gap-g2 mb-g3">
              <Cpu size={16} className="text-brand" />
              <h3 className="text-card-title text-brand">Fleet Health Status</h3>
            </div>
            {fleet.length > 0 ? (
              <div className={cn(cardSizing.scrollFill, "grid grid-cols-1 sm:grid-cols-2 gap-g2 content-start")}>
                {fleet.map((eq) => {
                  const meta = STATUS_META[eq.status];
                  return (
                    <Link
                      key={eq.equipment_id}
                      to={`/equipment/${eq.equipment_id}/edit`}
                      className={cn(
                        "rounded-lg border px-g3 py-g2 transition-all hover:-translate-y-0.5 hover:shadow-md",
                        meta.box
                      )}
                    >
                      <div className="flex items-center justify-between gap-g2">
                        <p className="font-semibold text-brand truncate">{eq.machine_name}</p>
                        <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", meta.dot)} />
                      </div>
                      <p className="text-xs text-muted-foreground truncate mt-g1">
                        {eq.plant_name} · {eq.area}
                      </p>
                      <div className="flex items-center justify-between mt-g2">
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

          <GlassCard equalHeight className={cardPad} delay={0.35}>
            <div className="flex items-center gap-g2 mb-g3">
              <AlertTriangle size={16} className="text-machine-warning" />
              <h3 className="text-card-title text-brand">Maintenance Alerts</h3>
            </div>
            {alerts.length > 0 ? (
              <>
                <div className={cn(cardSizing.scrollFill, "space-y-g2 pr-1")}>
                  {visibleAlerts.map((alert, i) => {
                    const meta = STATUS_META[alert.status as EquipmentHealthStatus] ?? STATUS_META.no_baseline;
                    return (
                      <div
                        key={`${alert.equipment_id}-${alert.channel}-${alert.feature_code}-${alertOffset + i}`}
                        className={cn("rounded-lg border px-g3 py-g2", meta.box)}
                      >
                        <div className="flex items-center justify-between gap-g2">
                          <p className="font-semibold text-brand text-sm truncate">{alert.machine_name}</p>
                          <span className={cn("text-xs font-semibold shrink-0", meta.text)}>{meta.label}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-g1">
                          {alert.feature_name ?? alert.feature_code} · CH-{alert.channel + 1} ·{" "}
                          {alert.value.toFixed(2)} {alert.unit}
                        </p>
                        <p className="text-xs text-muted-foreground mt-g1">{relativeTime(alert.computed_at)}</p>
                      </div>
                    );
                  })}
                </div>
                <PanelPagination
                  page={alertPage}
                  pageSize={alertsPerPage}
                  total={alerts.length}
                  onPageChange={setAlertPage}
                  label="alerts"
                />
              </>
            ) : (
              <IndustrialEmptyState message="No active alerts — fleet is within normal thresholds." />
            )}
          </GlassCard>
        </div>
      )}

      {hasFleet && (
        <GlassCard className={cardPad} delay={0.4}>
          <div className="flex items-center gap-g2 mb-g3">
            <Radio size={16} className="text-signal-dark" />
            <h3 className="text-card-title text-brand">Signal Analytics Feed</h3>
          </div>
          {data && data.recent_activity.length > 0 ? (
            <div className="space-y-g2">
              {data.recent_activity.map((activity) => (
                <div
                  key={activity.upload_id}
                  className="flex items-center justify-between gap-g3 px-g3 py-g2 rounded-lg bg-warm border border-border"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-brand truncate">{activity.machine_name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {activity.mounting_location} · {activity.original_filename ?? "manual capture"}
                    </p>
                  </div>
                  <div className="flex items-center gap-g3 shrink-0">
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

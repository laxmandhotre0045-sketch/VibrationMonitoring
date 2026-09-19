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
import { STATUS_TONES, toneForHealthStatus, type StatusTone } from "@/lib/status-box";
import { StatusBadge, StatusRail } from "@/components/ui/StatusBox";
import type { EquipmentHealthStatus } from "@/types/dashboard";

export function Dashboard() {
  const { data, isLoading, isError } = useDashboardSummary();

  const counts = data?.counts;
  const hasFleet = (counts?.total ?? 0) > 0;

  const fleet = data?.equipment_health ?? [];
  const alerts = data?.alerts ?? [];

  // Fleet Health Status and Maintenance Alerts share a `grid-golden` row, so
  // they have to end level. Neither list is a safe height on its own: alerts are
  // capped at 20 by the backend and equipment_health is not capped at all.
  //
  // Both panels therefore page to one shared row budget. The fleet grid is 2-up
  // from Tailwind's `sm` and 1-up below it, so it takes `rows x cols` per page
  // while the single-column alert list takes `rows`. Each renders its own pager
  // only when its list overflows that budget.
  const FLEET_ROW_CAP = 4;
  const fleetIsTwoUp = useMediaQuery("(min-width: 640px)");
  const fleetCols = fleetIsTwoUp ? 2 : 1;
  // A floor of 3 stops a two-machine fleet from squeezing the alerts beside it
  // down to a single row.
  const listRows = Math.max(3, Math.min(FLEET_ROW_CAP, Math.ceil(fleet.length / fleetCols)));

  const fleetPerPage = listRows * fleetCols;
  const fleetPageCount = Math.max(1, Math.ceil(fleet.length / fleetPerPage));
  const [fleetPage, setFleetPage] = useState(1);
  useEffect(() => {
    // Page size follows the viewport, so the current page can fall off the end
    // without the user touching anything.
    if (fleetPage > fleetPageCount) setFleetPage(fleetPageCount);
  }, [fleetPage, fleetPageCount]);
  const fleetOffset = (fleetPage - 1) * fleetPerPage;
  const visibleFleet = fleet.slice(fleetOffset, fleetOffset + fleetPerPage);

  const alertsPerPage = listRows;
  const alertPageCount = Math.max(1, Math.ceil(alerts.length / alertsPerPage));
  const [alertPage, setAlertPage] = useState(1);
  useEffect(() => {
    if (alertPage > alertPageCount) setAlertPage(alertPageCount);
  }, [alertPage, alertPageCount]);
  const alertOffset = (alertPage - 1) * alertsPerPage;
  const visibleAlerts = alerts.slice(alertOffset, alertOffset + alertsPerPage);

  // The feed is full width with no neighbour to match, so its page size is just
  // a height budget: half the backend's cap of 10, which keeps the card near the
  // height of the golden row above it instead of running past the fold.
  const activity = data?.recent_activity ?? [];
  const ACTIVITY_PER_PAGE = 5;
  const activityPageCount = Math.max(1, Math.ceil(activity.length / ACTIVITY_PER_PAGE));

  const [activityPage, setActivityPage] = useState(1);
  useEffect(() => {
    if (activityPage > activityPageCount) setActivityPage(activityPageCount);
  }, [activityPage, activityPageCount]);

  const activityOffset = (activityPage - 1) * ACTIVITY_PER_PAGE;
  const visibleActivity = activity.slice(activityOffset, activityOffset + ACTIVITY_PER_PAGE);

  // Each counter is lit in the colour of the state it counts, and dimmed when
  // that state is empty — a glowing red rail over "Critical 0" reads as an
  // alarm from across the room.
  const kpis: {
    label: string;
    value: string | number;
    icon: typeof Gauge;
    text: string;
    tone: StatusTone;
    dim: boolean;
  }[] = [
    {
      label: "Fleet Health",
      value: counts?.average_health_score != null ? `${counts.average_health_score}%` : "—",
      icon: Gauge,
      text: "text-brand",
      tone: "caution",
      dim: counts?.average_health_score == null,
    },
    {
      label: "Critical",
      value: counts ? counts.critical : "—",
      icon: AlertTriangle,
      text: "text-machine-critical",
      tone: "critical",
      dim: !counts?.critical,
    },
    {
      label: "Warning",
      value: counts ? counts.warning : "—",
      icon: Activity,
      text: "text-machine-warning",
      tone: "warning",
      dim: !counts?.warning,
    },
    {
      label: "Healthy",
      value: counts ? counts.normal : "—",
      icon: ShieldCheck,
      text: "text-machine-healthy",
      tone: "healthy",
      dim: !counts?.normal,
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
        <IndustrialEmptyState message="Unable to load fleet data. Check your connection and try again." />
      )}

      <PageSection title="Fleet Overview">
        <div className={gridMetrics}>
          {kpis.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <GlassCard
                key={stat.label}
                equalHeight
                delay={0.05 + i * 0.05}
                className={cn(cardPad, "relative overflow-hidden")}
              >
                <StatusRail tone={stat.tone} dim={stat.dim} className="w-[4px]" />
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
          <GlassCard equalHeight hover={false} className={cardPad} delay={0.3}>
            <div className="flex items-center gap-g2 mb-g3">
              <Cpu size={16} className="text-brand" />
              <h3 className="text-card-title text-brand">Fleet Health Status</h3>
            </div>
            {fleet.length > 0 ? (
              <>
                <div className={cn(cardSizing.scrollFill, "grid grid-cols-1 sm:grid-cols-2 gap-g2 content-start")}>
                  {visibleFleet.map((eq) => {
                    const meta = STATUS_META[eq.status];
                    const tone = toneForHealthStatus(eq.status);
                    return (
                      <Link
                        key={eq.equipment_id}
                        to={`/equipment/${eq.equipment_id}/edit`}
                        className={cn(
                          "relative overflow-hidden rounded-lg border border-border bg-white",
                          "px-g3 py-g2 pl-g4 transition-all hover:-translate-y-0.5 hover:shadow-md",
                          STATUS_TONES[tone].wash
                        )}
                      >
                        <StatusRail tone={tone} />
                        <div className="flex items-center justify-between gap-g2">
                          <p className="font-semibold text-brand truncate">{eq.machine_name}</p>
                          <StatusBadge tone={tone}>{meta.label}</StatusBadge>
                        </div>
                        <p className="text-xs text-muted-foreground truncate mt-g1">
                          {eq.plant_name} · {eq.area}
                        </p>
                        <div className="flex items-center justify-between gap-g2 mt-g2">
                          <span className="text-xs font-semibold text-brand">
                            {eq.health_score != null ? `Health ${eq.health_score}` : ""}
                          </span>
                          <span className="text-xs text-muted-foreground">{relativeTime(eq.last_upload_at)}</span>
                        </div>
                      </Link>
                    );
                  })}
                </div>
                <PanelPagination
                  page={fleetPage}
                  pageSize={fleetPerPage}
                  total={fleet.length}
                  onPageChange={setFleetPage}
                  label="machines"
                />
              </>
            ) : (
              <IndustrialEmptyState message="Loading fleet health data…" />
            )}
          </GlassCard>

          <GlassCard equalHeight hover={false} className={cardPad} delay={0.35}>
            <div className="flex items-center gap-g2 mb-g3">
              <AlertTriangle size={16} className="text-machine-warning" />
              <h3 className="text-card-title text-brand">Maintenance Alerts</h3>
            </div>
            {alerts.length > 0 ? (
              <>
                <div className={cn(cardSizing.scrollFill, "space-y-g2 pr-1")}>
                  {visibleAlerts.map((alert, i) => {
                    const status = (alert.status as EquipmentHealthStatus) ?? "no_baseline";
                    const meta = STATUS_META[status] ?? STATUS_META.no_baseline;
                    const tone = toneForHealthStatus(status);
                    return (
                      <div
                        key={`${alert.equipment_id}-${alert.channel}-${alert.feature_code}-${alertOffset + i}`}
                        className={cn(
                          "relative overflow-hidden rounded-lg border border-border bg-white",
                          "px-g3 py-g2 pl-g4 transition-all hover:-translate-y-0.5 hover:shadow-md",
                          STATUS_TONES[tone].wash
                        )}
                      >
                        <StatusRail tone={tone} />
                        <div className="flex items-center justify-between gap-g2">
                          <p className="font-semibold text-brand text-sm truncate">{alert.machine_name}</p>
                          <StatusBadge tone={tone}>{meta.label}</StatusBadge>
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
        <GlassCard hover={false} className={cardPad} delay={0.4}>
          <div className="flex items-center gap-g2 mb-g3">
            <Radio size={16} className="text-signal-dark" />
            <h3 className="text-card-title text-brand">Recent Uploads</h3>
          </div>
          {activity.length > 0 ? (
            <>
              <div className="space-y-g2">
                {visibleActivity.map((entry) => (
                  <div
                    key={entry.upload_id}
                    className="flex items-center justify-between gap-g3 px-g3 py-g2 rounded-lg bg-warm border border-border transition-all hover:-translate-y-0.5 hover:shadow-md hover:border-signal-light/50"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-brand truncate">{entry.machine_name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {entry.mounting_location} · {entry.original_filename ?? "manual capture"}
                      </p>
                    </div>
                    <div className="flex items-center gap-g3 shrink-0">
                      <span className="text-xs font-medium text-muted-foreground capitalize">
                        {entry.features_status}
                      </span>
                      <span className="text-xs text-muted-foreground">{relativeTime(entry.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
              <PanelPagination
                page={activityPage}
                pageSize={ACTIVITY_PER_PAGE}
                total={activity.length}
                onPageChange={setActivityPage}
                label="uploads"
              />
            </>
          ) : (
            <IndustrialEmptyState message="No sensor data uploaded yet. Upload from Equipment Master to see activity here." />
          )}
        </GlassCard>
      )}
    </div>
  );
}

import React from "react";
import { Activity, Brain, TrendingUp, Shield, LayoutDashboard, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { ComingSoon } from "@/components/layout/ComingSoon";
import { GlassCard } from "@/components/ui/GlassCard";
import { cardSizing } from "@/lib/card-sizing";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

const PREVIEW_STATS = [
  { label: "Fleet Health", value: "—", icon: Activity, accent: false },
  { label: "AI Predictions", value: "—", icon: Brain, accent: true },
  { label: "Anomaly Score", value: "—", icon: TrendingUp, accent: true },
  { label: "Uptime", value: "—", icon: Shield, accent: false },
];

export function Dashboard() {
  return (
    <div className="space-y-6">
      <ComingSoon
        title="Operations Dashboard"
        subtitle="Real-time fleet health, vibration insights, and predictive analytics across your industrial asset portfolio."
        icon={LayoutDashboard}
        features={[
          "Real-time vibration heatmaps",
          "Fleet-wide health scoring",
          "Signal analytics feed",
          "Predictive maintenance alerts",
        ]}
      />

      <div>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-bold text-brand tracking-tight">Fleet Overview</h2>
          <span className="text-sm font-semibold px-2 py-0.5 rounded-md bg-white text-signal-dark border border-signal-light/50">
            Preview
          </span>
        </div>
        <div className="h-0.5 w-10 bg-brand-accent rounded-full mb-4" />
        <div className={cn("grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4", cardSizing.gridEqual)}>
          {PREVIEW_STATS.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <GlassCard key={stat.label} equalHeight delay={0.05 + i * 0.05} className="p-5">
                <div className={cn(cardSizing.kpiBody, "gap-4")}>
                  <div className="w-9 h-9 rounded-lg bg-white border border-border flex items-center justify-center shrink-0">
                    <Icon size={18} className={stat.accent ? "text-signal-dark" : "text-brand"} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-kpi-value mb-0.5">{stat.value}</p>
                    <p className="text-base font-medium text-muted-foreground">{stat.label}</p>
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      </div>

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
    </div>
  );
}

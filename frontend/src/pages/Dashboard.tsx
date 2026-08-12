import React from "react";
import { Activity, Brain, TrendingUp, Shield, LayoutDashboard, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { ComingSoon } from "@/components/layout/ComingSoon";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";

const PREVIEW_STATS = [
  { label: "Fleet Health", value: "—", icon: Activity, accent: false },
  { label: "AI Predictions", value: "—", icon: Brain, accent: true },
  { label: "Anomaly Score", value: "—", icon: TrendingUp, accent: true },
  { label: "Uptime", value: "—", icon: Shield, accent: false },
];

export function Dashboard() {
  return (
    <div className="space-y-4 sm:space-y-6">
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
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
          <h2 className="text-base sm:text-lg font-bold text-brand">Fleet Overview</h2>
          <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-white text-signal-dark border border-signal-light/50 w-fit">
            Preview
          </span>
        </div>
        <div className="h-0.5 w-10 bg-brand-accent rounded-full mb-3 sm:mb-4" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {PREVIEW_STATS.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <GlassCard key={stat.label} delay={0.05 + i * 0.05} className="p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-9 h-9 rounded-lg bg-white border border-border flex items-center justify-center">
                    <Icon size={18} className={stat.accent ? "text-signal-dark" : "text-brand"} />
                  </div>
                </div>
                <p className="text-2xl font-bold text-border mb-0.5">{stat.value}</p>
                <p className="text-sm font-medium text-muted-foreground">{stat.label}</p>
              </GlassCard>
            );
          })}
        </div>
      </div>

      <GlassCard className="p-4 sm:p-5" delay={0.3}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex-1">
            <h3 className="text-sm sm:text-base font-bold text-brand">Start with Equipment Master Data</h3>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1 sm:mt-2">
              Register your assets to enable vibration intelligence and predictive maintenance.
            </p>
          </div>
          <Link to="/equipment" className="flex-shrink-0">
            <Button icon={<ArrowRight size={16} />}>Open Equipment Master</Button>
          </Link>
        </div>
      </GlassCard>
    </div>
  );
}

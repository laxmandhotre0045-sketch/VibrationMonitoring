import React from "react";
import { useFormContext } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Lightbulb,
  Radio,
  TrendingUp,
} from "lucide-react";
import { listEquipment } from "@/api/equipment";
import type { EquipmentFormData } from "@/types/equipment";
import {
  getAIReadinessScore,
  getFormCompletion,
  getMissingAlerts,
  getRecommendedActions,
  getSensorStatus,
} from "@/lib/form-intelligence";
import { cn } from "@/lib/utils";
import { cardSizing } from "@/lib/card-sizing";
import { cardHover } from "@/lib/card-hover";

interface AssetIntelligencePanelProps {
  activeStep: number;
}

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-g4 py-g3 border-b border-border last:border-0">
      <h4 className="text-overline text-brand mb-g3">{title}</h4>
      {children}
    </div>
  );
}

export function AssetIntelligencePanel({ activeStep }: AssetIntelligencePanelProps) {
  const { watch } = useFormContext<EquipmentFormData>();
  const data = watch();

  const { data: equipmentData } = useQuery({
    queryKey: ["equipment", "count"],
    queryFn: () => listEquipment({ page: 1, page_size: 1 }),
  });

  const aiScore = getAIReadinessScore(data);
  const completion = getFormCompletion(data);
  const alerts = getMissingAlerts(data);
  const sensorStatus = getSensorStatus(data);
  const actions = getRecommendedActions(data, activeStep);
  const equipmentCount = equipmentData?.total ?? 0;

  return (
    <aside className="sticky top-6">
      <div className={cn(
        "rounded-xl border border-border bg-white shadow-card overflow-hidden flex flex-col max-h-[calc(100vh-6rem)]",
        cardHover.panel
      )}>
        <div className="px-g4 py-g3 bg-brand text-white shrink-0">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-brand-accent" />
            <div>
              <h3 className="text-base font-bold">Asset Intelligence Panel</h3>
              <p className="text-sm font-medium text-white/85 mt-g1">Real-time profile analysis</p>
            </div>
          </div>
        </div>

        <div className={cardSizing.scrollFill}>
        <PanelSection title="AI Readiness Score">
          <div className="flex items-end justify-between mb-g2">
            <span className="text-3xl font-bold text-brand-accent-dark">{aiScore}%</span>
            <TrendingUp size={20} className="text-brand-accent mb-g1" />
          </div>
          <div className="h-2 bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-accent rounded-full transition-all duration-500"
              style={{ width: `${aiScore}%` }}
            />
          </div>
          <p className="text-sm font-medium text-muted-foreground mt-g2">
            {aiScore >= 70 ? "Ready for vibration intelligence" : "Additional data needed for AI diagnostics"}
          </p>
        </PanelSection>

        <PanelSection title="Form Completion">
          <div className="flex items-center justify-between mb-g2">
            <span className="text-2xl font-bold text-brand">{completion}%</span>
            <span className="text-sm font-medium text-muted-foreground">of profile complete</span>
          </div>
          <div className="h-2 bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-brand rounded-full transition-all duration-500"
              style={{ width: `${completion}%` }}
            />
          </div>
        </PanelSection>

        <PanelSection title="Fleet Context">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-background border border-border">
            <Cpu size={18} className="text-brand shrink-0" />
            <div>
              <p className="text-lg font-bold text-brand">{equipmentCount}</p>
              <p className="text-sm font-medium text-muted-foreground">Registered equipment</p>
            </div>
          </div>
        </PanelSection>

        <PanelSection title="Machine Type">
          <div className="flex items-center gap-2">
            {data.machine_type ? (
              <>
                <CheckCircle2 size={16} className="text-machine-healthy" />
                <span className="text-base font-semibold text-foreground">{data.machine_type}</span>
              </>
            ) : (
              <>
                <AlertTriangle size={16} className="text-brand-accent" />
                <span className="text-base font-medium text-muted-foreground">Not selected</span>
              </>
            )}
          </div>
          {data.machine_criticality && (
            <p className="text-sm font-medium text-muted-foreground mt-g2">
              Criticality: <span className="font-semibold text-foreground">{data.machine_criticality}</span>
            </p>
          )}
        </PanelSection>

        <PanelSection title="Sensor Configuration">
          <div className="flex items-center gap-2">
            <Radio size={16} className={cn(
              sensorStatus.status === "complete" && "text-machine-healthy",
              sensorStatus.status === "partial" && "text-brand-accent",
              sensorStatus.status === "empty" && "text-muted-foreground"
            )} />
            <span className="text-base font-medium text-foreground">{sensorStatus.label}</span>
          </div>
        </PanelSection>

        {alerts.length > 0 && (
          <PanelSection title="Missing Information">
            <ul className="space-y-g2">
              {alerts.slice(0, 5).map((alert) => (
                <li key={alert} className="flex items-start gap-2 text-sm font-medium text-foreground/90">
                  <AlertTriangle size={13} className="text-brand-accent shrink-0 mt-0.5" />
                  {alert}
                </li>
              ))}
              {alerts.length > 5 && (
                <li className="text-sm font-medium text-muted-foreground pl-5">+{alerts.length - 5} more items</li>
              )}
            </ul>
          </PanelSection>
        )}

        <PanelSection title="Recommended Next Actions">
          <ul className="space-y-g2">
            {actions.map((action, i) => (
              <li key={i} className="flex items-start gap-2 text-sm font-medium text-foreground leading-relaxed">
                <Lightbulb size={13} className="text-brand-accent shrink-0 mt-0.5" />
                {action}
              </li>
            ))}
          </ul>
        </PanelSection>
        </div>
      </div>
    </aside>
  );
}

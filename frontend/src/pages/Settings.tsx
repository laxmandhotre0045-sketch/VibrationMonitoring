import React, { useState } from "react";
import { Settings } from "lucide-react";
import { PageHero } from "@/components/layout/PageHero";
import { ComingSoon } from "@/components/layout/ComingSoon";
import { SettingsTabNav } from "@/components/settings/SettingsTabNav";
import { VibrationSettingsModule } from "@/components/settings/vibration/VibrationSettingsModule";
import type { SettingsModuleId } from "@/types/vibration-settings";
import { analysisPageStack } from "@/components/analysis/analysis-layout";

export function SettingsPage() {
  const [activeModule, setActiveModule] = useState<SettingsModuleId>("vibration");

  return (
    <div className={analysisPageStack}>
      <PageHero
        title="Settings"
        subtitle="Platform configuration for industrial monitoring — device acquisition, channel mapping, alarm thresholds, and integrations."
        breadcrumbs={[{ label: "Home", href: "/" }, { label: "Settings" }]}
        vibrationBg
      />

      <SettingsTabNav activeModule={activeModule} onModuleChange={setActiveModule} />

      {activeModule === "vibration" ? (
        <VibrationSettingsModule />
      ) : (
        <ComingSoon
          title="Platform Settings"
          subtitle="User management, plant hierarchy, notification rules, and integration settings."
          icon={Settings}
          features={[
            "Role-based access control",
            "Plant & area hierarchy",
            "Notification rules",
            "API & webhook integrations",
          ]}
        />
      )}
    </div>
  );
}

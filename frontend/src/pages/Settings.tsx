import React, { useState } from "react";
import { PageHero } from "@/components/layout/PageHero";
import { SettingsTabNav } from "@/components/settings/SettingsTabNav";
import { VibrationSettingsModule } from "@/components/settings/vibration/VibrationSettingsModule";
import { PlatformSettingsModule } from "@/components/settings/platform/PlatformSettingsModule";
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

      {activeModule === "vibration" ? <VibrationSettingsModule /> : <PlatformSettingsModule />}
    </div>
  );
}

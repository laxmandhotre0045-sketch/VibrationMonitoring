import React from "react";
import { Settings } from "lucide-react";
import { ComingSoon } from "@/components/layout/ComingSoon";

export function SettingsPage() {
  return (
    <ComingSoon
      title="Settings"
      subtitle="Platform configuration — user management, plant hierarchy, notification rules, and integration settings."
      icon={Settings}
      features={[
        "Role-based access control",
        "Plant & area hierarchy",
        "Alert threshold configuration",
        "API & webhook integrations",
      ]}
    />
  );
}

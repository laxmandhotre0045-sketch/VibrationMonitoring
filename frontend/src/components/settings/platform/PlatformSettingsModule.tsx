import React, { useState } from "react";
import { Factory, Lock, Plug, Users, type LucideIcon } from "lucide-react";
import { UsersSection } from "./UsersSection";
import { PlantsSection } from "./PlantsSection";
import { IntegrationsSection } from "./IntegrationsSection";
import { useAuth } from "@/contexts/AuthContext";
import { ADMIN_ROLES } from "@/lib/role-access";
import { cn } from "@/lib/utils";
import type { PlatformSectionId } from "@/types/platform";

interface PlatformSection {
  id: PlatformSectionId;
  label: string;
  description: string;
  icon: LucideIcon;
}

const SECTIONS: PlatformSection[] = [
  {
    id: "users",
    label: "Users",
    description: "Accounts and roles",
    icon: Users,
  },
  {
    id: "plants",
    label: "Plants",
    description: "Sites, areas & lines",
    icon: Factory,
  },
  {
    id: "integrations",
    label: "Integrations",
    description: "API keys & webhooks",
    icon: Plug,
  },
];

export function PlatformSettingsModule() {
  const [active, setActive] = useState<PlatformSectionId>("users");
  const { hasRole } = useAuth();

  // The endpoints behind all three sections are admin-only, so a non-admin
  // would otherwise land on a page of 403s.
  if (!hasRole(ADMIN_ROLES)) {
    return (
      <div className="rounded-xl border border-border bg-[#FFFDF8] px-g4 py-g6 text-center shadow-[0_2px_14px_rgba(21,54,109,0.07)]">
        <span className="mx-auto mb-g3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand/[0.06] text-brand/60">
          <Lock size={22} />
        </span>
        <h2 className="text-base font-bold text-brand">Administrator access required</h2>
        <p className="mx-auto mt-g2 max-w-md text-sm text-muted-foreground leading-relaxed">
          User accounts, the plant hierarchy and integration credentials can only be managed by an
          administrator. Ask one of your platform admins if you need a change here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-g4">
      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label="Platform settings sections"
      >
        {SECTIONS.map((section) => {
          const isActive = active === section.id;
          const Icon = section.icon;

          return (
            <button
              key={section.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActive(section.id)}
              className={cn(
                "group inline-flex items-center gap-2.5 rounded-[10px] border px-4 py-2.5 text-left text-sm font-semibold transition-all duration-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45 focus-visible:ring-offset-2",
                isActive
                  ? "border-transparent bg-white text-signal-dark shadow-[0_8px_22px_rgba(255,107,0,0.12)] ring-1 ring-signal-light/35"
                  : "border-border bg-white/70 text-brand/75 hover:border-signal-light/50 hover:bg-warm hover:text-brand"
              )}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                  isActive
                    ? "bg-[#FFA500]/15 text-[#FFA500]"
                    : "bg-brand/[0.05] text-brand/50 group-hover:text-signal-dark"
                )}
              >
                <Icon size={17} strokeWidth={isActive ? 2.25 : 2} aria-hidden />
              </span>
              <span>
                <span className="block">{section.label}</span>
                <span className="block text-xs font-medium text-muted-foreground">
                  {section.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {active === "users" && <UsersSection />}
      {active === "plants" && <PlantsSection />}
      {active === "integrations" && <IntegrationsSection />}
    </div>
  );
}

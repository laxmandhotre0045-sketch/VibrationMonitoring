import React from "react";
import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { HeroIntelligenceBg } from "@/components/brand/HeroIntelligenceBg";
import { cn } from "@/lib/utils";

interface Breadcrumb {
  label: string;
  href?: string;
}

interface PageHeroProps {
  title: string;
  subtitle: string;
  breadcrumbs?: Breadcrumb[];
  equipmentCount?: number;
  actions?: React.ReactNode;
  /** Engineering waveform backdrop for reliability-domain pages */
  vibrationBg?: boolean;
}

export function PageHero({
  title,
  subtitle,
  breadcrumbs,
  equipmentCount,
  actions,
  vibrationBg = false,
}: PageHeroProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className={cn(
        "relative",
        vibrationBg && "content-card overflow-hidden"
      )}
    >
      {vibrationBg && <HeroIntelligenceBg />}

      <div className={cn("relative z-10", vibrationBg && "card-pad")}>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className="flex items-center gap-g1 mb-g2 text-sm font-medium">
            {breadcrumbs.map((crumb, i) => (
              <React.Fragment key={crumb.label}>
                {i > 0 && <ChevronRight size={14} className="text-muted-foreground" />}
                {crumb.href ? (
                  <Link to={crumb.href} className="text-muted-foreground hover:text-brand transition-colors">
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-brand font-semibold">{crumb.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
        )}

        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-g4">
          <div className="min-w-0">
            <h1 className="text-page-title lg:text-4xl">{title}</h1>
            <div className="brand-divider mt-g1" />
            <p className="text-helper max-w-2xl mt-g2">{subtitle}</p>
          </div>

          {/* Four of the five heroes pass neither actions nor a count. Rendering
              the container unconditionally cost them a full gap-g4 of dead space
              once the row stacked on mobile. */}
          {(equipmentCount !== undefined || actions) && (
            <div className="flex flex-wrap items-center gap-g2">
              {equipmentCount !== undefined && (
                <div className="flex items-center gap-g2 px-g3 py-g2 rounded-lg bg-white/90 border border-border shadow-card backdrop-blur-[2px]">
                  <div>
                    <p className="text-overline">Equipment</p>
                    <p className="text-kpi-value text-brand">{equipmentCount.toLocaleString()}</p>
                  </div>
                </div>
              )}
              {actions}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

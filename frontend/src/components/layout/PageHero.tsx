import React from "react";
import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { VibrationIntelligenceBg } from "@/components/brand/VibrationIntelligenceBg";
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
        "relative mb-6",
        vibrationBg && "content-card overflow-hidden"
      )}
    >
      {vibrationBg && <VibrationIntelligenceBg />}

      <div className={cn("relative z-10", vibrationBg && "px-6 lg:px-8 py-6 lg:py-7")}>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className="flex items-center gap-1.5 mb-3 text-sm">
            {breadcrumbs.map((crumb, i) => (
              <React.Fragment key={crumb.label}>
                {i > 0 && <ChevronRight size={14} className="text-muted-foreground" />}
                {crumb.href ? (
                  <Link to={crumb.href} className="text-muted-foreground hover:text-brand transition-colors font-medium">
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-brand font-semibold">{crumb.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
        )}

        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
          <div className="space-y-1">
            <h1 className="text-3xl lg:text-4xl font-bold tracking-tight text-brand">{title}</h1>
            <div className="brand-divider" />
            <p className="text-base text-muted-foreground max-w-2xl leading-relaxed pt-2">{subtitle}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {equipmentCount !== undefined && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/90 border border-border shadow-card backdrop-blur-[2px]">
                <div>
                  <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Equipment</p>
                  <p className="text-xl font-bold text-brand">{equipmentCount.toLocaleString()}</p>
                </div>
              </div>
            )}

            {actions}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

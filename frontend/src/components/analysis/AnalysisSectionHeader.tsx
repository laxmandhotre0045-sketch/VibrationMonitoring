import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { analysisSectionIconBoxClass, analysisSectionIconSize } from "./analysis-layout";

interface AnalysisSectionHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  className?: string;
}

export function AnalysisSectionHeader({
  icon: Icon,
  title,
  subtitle,
  className,
}: AnalysisSectionHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 mb-3 pb-2 border-b border-border",
        className
      )}
    >
      <span className={analysisSectionIconBoxClass}>
        <Icon size={analysisSectionIconSize} strokeWidth={2} aria-hidden />
      </span>
      <div className="min-w-0">
        <h2 className="text-base font-bold text-foreground leading-tight">{title}</h2>
        {subtitle && (
          <p className="text-sm text-muted-foreground mt-0.5 leading-snug">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

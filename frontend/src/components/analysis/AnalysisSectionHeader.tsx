import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

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
      <span className="w-8 h-8 rounded-md bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0">
        <Icon size={14} aria-hidden />
      </span>
      <div className="min-w-0">
        <h2 className="text-lg font-bold text-foreground leading-tight">{title}</h2>
        {subtitle && (
          <p className="text-sm text-muted-foreground mt-0.5 leading-snug">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

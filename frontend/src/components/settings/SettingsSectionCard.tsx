import React from "react";
import { cn } from "@/lib/utils";
import { analysisSectionIconBoxClass } from "@/components/analysis/analysis-layout";

interface SettingsSectionCardProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function SettingsSectionCard({
  title,
  description,
  icon,
  children,
  className,
  bodyClassName,
}: SettingsSectionCardProps) {
  return (
    <section
      className={cn(
        "content-card rounded-xl border border-border bg-[#FFFDF8] shadow-[0_2px_14px_rgba(21,54,109,0.07)]",
        className
      )}
    >
      <div className="flex items-start gap-3 border-b border-border px-4 py-4 sm:px-5">
        {icon && (
          <span className={cn(analysisSectionIconBoxClass, "w-10 h-10")}>{icon}</span>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-bold text-brand leading-tight">{title}</h2>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground leading-snug">{description}</p>
          )}
        </div>
      </div>
      <div className={cn("p-4 sm:p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

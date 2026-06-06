import React from "react";
import { cn } from "@/lib/utils";

interface SectionCardProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  delay?: number;
}

export function SectionCard({ title, description, icon, children, className }: SectionCardProps) {
  return (
    <div className={cn("content-card", className)}>
      <div className="px-8 pt-8 pb-0">
        <div className="flex items-center gap-3">
          {icon && (
            <span className="w-10 h-10 rounded-lg bg-[#FFA500]/10 border border-[#FFA500]/30 flex items-center justify-center text-[#FFA500] shrink-0">
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h3 className="text-xl font-semibold text-foreground tracking-tight">{title}</h3>
            {description && (
              <p className="text-base text-muted-foreground mt-1 leading-relaxed">{description}</p>
            )}
          </div>
        </div>
      </div>
      <div className="p-8">{children}</div>
    </div>
  );
}

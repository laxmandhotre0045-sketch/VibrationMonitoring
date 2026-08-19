import React from "react";
import { cn } from "@/lib/utils";
import { cardSizing } from "@/lib/card-sizing";
import { cardHover } from "@/lib/card-hover";

interface SectionCardProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  delay?: number;
  /** Equal-height mode — only for intentional KPI-style rows. @see CARD_SIZING.md */
  equalHeight?: boolean;
  /** Internal scroll for long/dynamic content. @see CARD_SIZING.md */
  scrollBody?: boolean;
  /** Subtle hover feedback. Default: true */
  hover?: boolean;
  /** Pointer cursor — only when section is clickable. Default: false */
  interactive?: boolean;
}

/** Form/content section card — auto height, passive hover by default. */
export function SectionCard({
  title,
  description,
  icon,
  children,
  className,
  equalHeight = false,
  scrollBody = false,
  hover = true,
  interactive = false,
}: SectionCardProps) {
  return (
    <div
      className={cn(
        "content-card card-auto",
        hover && (interactive ? cardHover.interactive : cardHover.soft),
        equalHeight && cardSizing.equal,
        className
      )}
    >
      <div className="card-pad pb-0 shrink-0">
        <div className="flex items-center gap-g2">
          {icon && (
            <span className="w-9 h-9 rounded-lg bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0">
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h3 className="text-section-title">{title}</h3>
            {description && <p className="text-helper mt-g1">{description}</p>}
          </div>
        </div>
      </div>
      <div
        className={cn(
          "card-pad pt-g3",
          equalHeight && "flex-1 min-h-0",
          scrollBody && cardSizing.scrollSm
        )}
      >
        {children}
      </div>
    </div>
  );
}

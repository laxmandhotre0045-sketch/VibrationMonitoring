import React from "react";
import { cn } from "@/lib/utils";

interface PageSectionProps {
  title: string;
  /** Optional one-line context under the title. */
  description?: string;
  /** Right-aligned controls — filters, links, buttons. */
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/**
 * A titled band of a page.
 *
 * Replaces the header each page used to hand-roll. The dashboard's version was
 * an `h2` with `mb-4`, then a divider rule also with `mb-4` — 32px of dead air
 * between a heading and the content it labels, and a different amount on every
 * other page.
 *
 * Here the rule sits inline with the title rather than under it, so the header
 * costs one row instead of three, and the gap to the body is a single rung of
 * the ladder (13px).
 */
export function PageSection({
  title,
  description,
  actions,
  children,
  className,
}: PageSectionProps) {
  return (
    <section className={cn("w-full", className)}>
      <div className="flex items-end justify-between gap-g3 mb-g3">
        <div className="min-w-0">
          <div className="flex items-center gap-g2">
            <h2 className="text-section-title">{title}</h2>
            {/* Inline accent rule — absorbs the leftover width on the title
                row instead of claiming a row of its own. */}
            <span className="h-px flex-1 min-w-[1.5rem] signal-gradient opacity-40" />
          </div>
          {description && <p className="text-helper mt-g1">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-g2 shrink-0">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

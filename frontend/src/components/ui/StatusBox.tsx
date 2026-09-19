import React from "react";
import { STATUS_TONES, type StatusTone } from "@/lib/status-box";
import { cn } from "@/lib/utils";

/**
 * The lit edge of a status surface.
 *
 * The parent must be `relative overflow-hidden` — the rail is absolutely
 * positioned so it spans the full height whatever the card contains, which a
 * left border cannot do once the card has rounded corners and a wash.
 */
export function StatusRail({
  tone,
  dim = false,
  className,
}: {
  tone: StatusTone;
  /** Half-light for a state that is real but currently counts zero. */
  dim?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "absolute left-0 top-0 h-full w-[3px]",
        STATUS_TONES[tone].rail,
        dim && "opacity-35",
        className
      )}
    />
  );
}

/** Status as a solid filled box, readable at a glance where a dot is not. */
export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded px-2 py-0.5",
        "text-[10px] font-bold uppercase leading-4 tracking-wide",
        STATUS_TONES[tone].chip,
        className
      )}
    >
      {children}
    </span>
  );
}

/**
 * A card lit from its left edge by status: rail, wash and rounded clipping in
 * one wrapper, so every list row that carries a status looks the same.
 */
export function StatusSurface({
  tone,
  className,
  children,
}: {
  tone: StatusTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border bg-white",
        STATUS_TONES[tone].wash,
        className
      )}
    >
      <StatusRail tone={tone} />
      {children}
    </div>
  );
}

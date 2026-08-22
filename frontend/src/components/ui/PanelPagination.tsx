import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface PanelPaginationProps {
  /** 1-based. */
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Plural noun for the range readout, e.g. "alerts". */
  label?: string;
  className?: string;
}

/**
 * Footer pager for a card whose list would otherwise outgrow its neighbour.
 *
 * Sits after a `cardSizing.scrollFill` body inside an `equalHeight` card, so
 * the list stays bounded and the card ends level with the other panel in a
 * `grid-golden` row. Renders nothing when everything fits on one page.
 */
export function PanelPagination({
  page,
  pageSize,
  total,
  onPageChange,
  label = "items",
  className,
}: PanelPaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (pageCount <= 1) return null;

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  const step = cn(
    "inline-flex items-center justify-center w-7 h-7 rounded-lg",
    "border border-border bg-white text-muted-foreground transition-colors",
    "hover:text-brand hover:border-signal-light hover:bg-surface-hover",
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(245,166,35,0.22)]",
    "disabled:opacity-40 disabled:cursor-not-allowed",
    "disabled:hover:bg-white disabled:hover:border-border disabled:hover:text-muted-foreground"
  );

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-g2 mt-g3 pt-g3 border-t border-border",
        className
      )}
    >
      <p className="text-xs text-muted-foreground tabular-nums">
        {first}–{last} of {total} {label}
      </p>
      <div className="flex items-center gap-g1">
        <button
          type="button"
          className={step}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={`Previous page of ${label}`}
        >
          <ChevronLeft size={15} />
        </button>
        <span className="px-g1 text-xs font-semibold text-foreground tabular-nums">
          {page} / {pageCount}
        </span>
        <button
          type="button"
          className={step}
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label={`Next page of ${label}`}
        >
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}

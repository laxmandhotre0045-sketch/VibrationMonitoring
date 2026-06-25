import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { cardSizing } from "@/lib/card-sizing";
import { cardHover } from "@/lib/card-hover";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  /** Enable subtle hover feedback. Default: true */
  hover?: boolean;
  /** Pointer cursor — only when the card is clickable. Default: false */
  interactive?: boolean;
  glow?: boolean;
  delay?: number;
  /**
   * Equal-height mode — stretch to match the tallest card in the row.
   * Requires `cardSizing.gridEqual` on the parent grid.
   * @see src/components/ui/CARD_SIZING.md
   */
  equalHeight?: boolean;
  /**
   * Scrollable body for tables, long lists, feeds.
   * @see src/components/ui/CARD_SIZING.md
   */
  scrollable?: boolean;
}

/** Enterprise card — auto height, passive hover by default. */
export function GlassCard({
  children,
  className,
  hover = true,
  interactive = false,
  delay = 0,
  equalHeight = false,
  scrollable = false,
}: GlassCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
      className={cn(
        "content-card card-auto",
        hover &&
          (interactive
            ? cardHover.interactive
            : equalHeight
              ? cardHover.kpi
              : cardHover.passive),
        equalHeight && cardSizing.equal,
        scrollable && "overflow-hidden",
        className
      )}
    >
      {scrollable ? (
        <div className={cn(cardSizing.scroll, "flex-1 min-h-0")}>{children}</div>
      ) : (
        children
      )}
    </motion.div>
  );
}

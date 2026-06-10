/**
 * Enterprise card hover tokens — SensoVibe design system.
 * @see src/components/ui/CARD_HOVER.md
 */
export const cardHover = {
  /** Dashboard surfaces — tables, filters, summary cards (cursor: default) */
  passive: "card-hover",
  /** Form section cards — softer depth to avoid distraction during entry */
  soft: "card-hover-soft",
  /** KPI / stat cards — slightly stronger elevation */
  kpi: "card-hover-kpi",
  /** Visual hover + pointer — clickable dashboard widgets */
  interactive: "card-hover-interactive",
  /** Bordered panels without content-card gradient ring */
  panel: "panel-hover",
  /** Dashed upload / drop zones */
  upload: "card-hover-upload",
} as const;

export type CardHoverClass = (typeof cardHover)[keyof typeof cardHover];

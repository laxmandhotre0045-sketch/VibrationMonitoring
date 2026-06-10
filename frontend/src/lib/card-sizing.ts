/**
 * Card sizing design tokens.
 * @see src/components/ui/CARD_SIZING.md
 */
export const cardSizing = {
  /** Default — height follows content (form cards, section cards) */
  auto: "card-auto",
  /** Opt-in — stretch to match tallest sibling in a row */
  equal: "card-equal",
  /** Apply to grid/flex row when children use `equal` */
  gridEqual: "card-grid-equal",
  /** Scrollable body — tables, long lists (max ~70vh) */
  scroll: "card-scroll-region",
  /** Scrollable body — medium dynamic sections (max ~60vh) */
  scrollSm: "card-scroll-region-sm",
  /** Scrollable body — fills remaining height inside a capped panel */
  scrollFill: "card-scroll-fill",
  /** KPI/stat row inner layout */
  kpiBody: "card-kpi-body",
  /** Centered empty/loading states */
  stateCenter: "card-state-center",
} as const;

export type CardSizingClass = (typeof cardSizing)[keyof typeof cardSizing];

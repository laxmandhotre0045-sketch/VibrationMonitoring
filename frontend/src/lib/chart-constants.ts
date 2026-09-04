/** Primary diagnostic / analysis chart height (industrial monitoring standard). */
export const GRAPH_PRIMARY_HEIGHT = 580;

/** Compact chart height for health metric cards and dashboard tiles. */
export const GRAPH_COMPACT_HEIGHT = 220;

/** Minimum height when entering fullscreen mode. */
export const GRAPH_FULLSCREEN_MIN_HEIGHT = 400;

/**
 * KPI trend-card chart height. Taller than GRAPH_COMPACT_HEIGHT so the ten
 * feature trends read as monitoring charts rather than sparklines: the plot
 * keeps room for gridlines, per-sample markers, and the time-range slider
 * without any of them crowding the trace.
 */
export const GRAPH_KPI_CARD_HEIGHT = 340;

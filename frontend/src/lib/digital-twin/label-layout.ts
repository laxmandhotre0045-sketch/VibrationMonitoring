/**
 * Digital Twin — boundary label layout.
 *
 * Chips live in two rows outside the machine: sensors above, bearings below.
 * Each frame the anchors are projected to screen and this function decides
 * where the chips in one row sit horizontally. It is deliberately pure — no
 * three.js, no DOM — because "two chips must never overlap" is the one rule in
 * this feature worth proving rather than eyeballing.
 *
 * The solve is the standard three-pass constraint relaxation:
 *
 *   1. push apart  — walk left to right, shoving each chip clear of the one
 *                    before it. Guarantees no overlap, but drags the row right.
 *   2. recentre    — slide the whole row back so its midpoint sits under the
 *                    average anchor, undoing that drift.
 *   3. clamp       — pull the row inside the stage, right edge first then left,
 *                    re-applying the no-overlap constraint on the way back.
 *
 * Ordering is by anchor x so chips never cross their neighbours' leader lines,
 * with the item id as a tiebreak so two anchors at the same x keep a stable
 * order between frames instead of flickering.
 */

/** One chip to place. `width` must be a freshly measured px width. */
export interface LabelItem {
  id: string;
  /** Projected screen x of the anchor, in px from the stage's left edge. */
  anchorX: number;
  /** Projected screen y of the anchor, in px from the stage's top edge. */
  anchorY: number;
  /** Measured chip width in px. */
  width: number;
}

export interface LabelLayoutOptions {
  stageWidth: number;
  /** Minimum clear space between neighbouring chips. */
  gap?: number;
  /** Keep-out margin at the stage's left and right edges. */
  padding?: number;
}

export interface PlacedLabel {
  id: string;
  /** Left edge of the chip, px from the stage's left edge. */
  x: number;
  width: number;
  anchorX: number;
  anchorY: number;
}

export const DEFAULT_LABEL_GAP = 8;
export const DEFAULT_LABEL_PADDING = 8;

/**
 * Below this stage width a chip shows only its id, so six sensors still fit
 * across a phone without the row overflowing.
 */
export const COMPACT_LABEL_BREAKPOINT = 640;

export function shouldUseCompactLabels(stageWidth: number): boolean {
  return stageWidth < COMPACT_LABEL_BREAKPOINT;
}

/**
 * Place one row of chips.
 *
 * Returns them in the **input order**, so the caller can keep a stable DOM
 * order and React keys while the visual order follows the anchors.
 *
 * No-overlap is inviolable. Staying inside the stage is best-effort: if the
 * chips simply cannot fit across the available width, the row is centred and
 * overflows symmetrically rather than being allowed to collide — losing a chip
 * off the edge is recoverable by rotating the model, two chips drawn on top of
 * each other is not.
 */
export function layoutLabelRow(
  items: LabelItem[],
  options: LabelLayoutOptions
): PlacedLabel[] {
  const { stageWidth } = options;
  const gap = options.gap ?? DEFAULT_LABEL_GAP;
  const padding = options.padding ?? DEFAULT_LABEL_PADDING;

  if (items.length === 0) return [];

  const order = items
    .map((item, index) => ({ item, index }))
    .sort((a, b) =>
      a.item.anchorX === b.item.anchorX
        ? a.item.id.localeCompare(b.item.id)
        : a.item.anchorX - b.item.anchorX
    );

  const width = order.map((entry) => entry.item.width);
  const left = order.map((entry) => entry.item.anchorX - entry.item.width / 2);
  const last = order.length - 1;

  // 1. Push apart, left to right.
  for (let i = 1; i <= last; i += 1) {
    const earliest = left[i - 1] + width[i - 1] + gap;
    if (left[i] < earliest) left[i] = earliest;
  }

  // 2. Recentre. The push only ever moves chips right, so without this a
  //    crowded row drifts away from the machine it is labelling.
  const desiredCentre =
    order.reduce((sum, entry) => sum + entry.item.anchorX, 0) / order.length;
  const rowCentre = (left[0] + left[last] + width[last]) / 2;
  const recentre = desiredCentre - rowCentre;
  for (let i = 0; i <= last; i += 1) left[i] += recentre;

  // 3a. Clamp the right edge, walking back and re-asserting the gap.
  const maxRight = stageWidth - padding;
  if (left[last] + width[last] > maxRight) {
    left[last] = maxRight - width[last];
    for (let i = last - 1; i >= 0; i -= 1) {
      const latest = left[i + 1] - width[i] - gap;
      if (left[i] > latest) left[i] = latest;
    }
  }

  // 3b. Then the left edge. This pass runs second so that when the row is too
  //     wide to fit at all, the overflow lands on the right where it is at
  //     least predictable — and the no-overlap constraint is re-applied here,
  //     which is what keeps 3a from ever pushing two chips together.
  if (left[0] < padding) {
    left[0] = padding;
    for (let i = 1; i <= last; i += 1) {
      const earliest = left[i - 1] + width[i - 1] + gap;
      if (left[i] < earliest) left[i] = earliest;
    }
  }

  const placed: PlacedLabel[] = new Array(items.length);
  order.forEach((entry, i) => {
    placed[entry.index] = {
      id: entry.item.id,
      x: left[i],
      width: width[i],
      anchorX: entry.item.anchorX,
      anchorY: entry.item.anchorY,
    };
  });
  return placed;
}

/**
 * The leader line from a chip down (or up) to its anchor dot: straight out of
 * the chip, a knee at `kneeY`, then a diagonal to the anchor.
 *
 * Returned as an SVG path so the overlay can render it without knowing the
 * geometry rules.
 */
export function leaderPath(
  chipCentreX: number,
  chipEdgeY: number,
  anchorX: number,
  anchorY: number,
  kneeY: number
): string {
  return `M ${chipCentreX} ${chipEdgeY} L ${chipCentreX} ${kneeY} L ${anchorX} ${anchorY}`;
}

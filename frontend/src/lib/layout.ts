/**
 * Layout tokens — the one spacing vocabulary for every page.
 *
 * Before this, three systems were in play: Dashboard stacked with `space-y-6`,
 * EquipmentMasterList hand-placed `mb-8` / `mb-6` / `mt-6`, and analysis had
 * its own `analysis-layout.ts` on `space-y-4`. Nothing lined up across pages
 * because nothing shared a source.
 *
 * Every value here resolves to a rung of the Fibonacci ladder in
 * `tailwind.config.js` (4, 8, 13, 21, 34, 55). Reach for a token, not a number —
 * a raw `gap-5` in a page is the bug this module exists to prevent.
 */

/** Outermost page wrapper: caps width, centres, sets section rhythm. */
export const pageShell = "page-shell page-stack";

/** Vertical rhythm between top-level sections (34px). */
export const pageStack = "page-stack";

/** Vertical rhythm between blocks inside a section or card (21px). */
export const sectionStack = "section-stack";

/** Gap between sibling cards in a grid (13px). */
export const gridGap = "gap-g3";

/** Gap between related controls on one row (8px). */
export const controlGap = "gap-g2";

/** Interior padding of a card (21px). */
export const cardPad = "card-pad";

/** Interior padding for dense cards — filter bars, compact panels (13px). */
export const cardPadTight = "card-pad-tight";

/**
 * Primary/secondary column pair at the true golden split (61.8 / 38.2).
 * Collapses to a single column below `lg`.
 */
export const gridGolden = "grid-golden";

/** Same split, minor column first. */
export const gridGoldenReverse = "grid-golden grid-golden-reverse";

/**
 * Equal-width metric row. Four is the practical ceiling — beyond that the
 * cards fall under the ~220px where a value and its label stop reading as a
 * pair.
 */
export const gridMetrics = "grid grid-cols-2 lg:grid-cols-4 gap-g3 items-stretch";

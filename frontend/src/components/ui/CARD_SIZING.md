# Card Sizing Standard

Global rules for `GlassCard`, `SectionCard`, and `content-card` surfaces.

## Default component

| Use case | Component |
|----------|-----------|
| Dashboard / list KPIs, filters, table wrappers | `GlassCard` |
| Form sections, review blocks | `SectionCard` |
| Custom inline surfaces | `content-card` + utilities from `cardSizing` |

**Default behavior is auto height.** Cards size to their content. No prop is required.

## Height categories

### 1. Auto height (default)

- Height is determined by content.
- Use for **all form cards** and most content cards.
- `SectionCard` and `GlassCard` use this unless a mode below is enabled.

```tsx
<SectionCard title="Location Hierarchy">...</SectionCard>
<GlassCard className="p-5">...</GlassCard>
```

### 2. Equal height (opt-in)

- Use only when a **row of cards must align visually** (e.g. KPI/stat tiles).
- Enable on the card **and** on the parent grid.

```tsx
import { cardSizing } from "@/lib/card-sizing";

<div className={cn("grid grid-cols-4 gap-4", cardSizing.gridEqual)}>
  <GlassCard equalHeight className="p-5">...</GlassCard>
</div>
```

**Do not** use `equalHeight` on form section cards in multi-column grids.

### 3. Scrollable (opt-in)

- Use only for **dynamic or long content**: tables, sensor lists, AI insights, activity feeds.
- Does not make every card scrollable.

| Prop / utility | When to use |
|----------------|-------------|
| `GlassCard` + `scrollable` | Table wrapper inside a card |
| `SectionCard` + `scrollBody` | Long dynamic form lists |
| `cardSizing.scroll` | Direct `content-card` table region |
| `cardSizing.scrollSm` | Medium dynamic sections |
| `cardSizing.scrollFill` | Panel body inside `max-h-*` container |

```tsx
<SectionCard title="Additional Sensors" scrollBody>...</SectionCard>

<GlassCard hover={false}>
  <div className={cardSizing.scroll}>
    <table>...</table>
  </div>
</GlassCard>
```

## Utilities (`src/lib/card-sizing.ts`)

| Token | Class | Purpose |
|-------|-------|---------|
| `auto` | `card-auto` | Explicit content-based height |
| `equal` | `card-equal` | Equal-height card shell |
| `gridEqual` | `card-grid-equal` | Parent row stretch for equal-height children |
| `scroll` | `card-scroll-region` | Large scroll region |
| `scrollSm` | `card-scroll-region-sm` | Medium scroll region |
| `scrollFill` | `card-scroll-fill` | Fill parent + scroll |
| `kpiBody` | `card-kpi-body` | KPI inner layout |
| `stateCenter` | `card-state-center` | Loading / empty states |

## Decision guide

| Content | Mode |
|---------|------|
| Form fields (Location, Machine ID, Manufacturer, Image upload) | **Auto** |
| Asset Preview sidebar | **Auto** |
| KPI / statistic row | **Equal height** + `gridEqual` |
| Equipment table | **Scroll** (`cardSizing.scroll`) |
| Additional sensors list | **Scroll** (`scrollBody`) |
| Sensors review on save tab | **Scroll** (`scrollBody`) |
| AI intelligence panel | **Scroll fill** inside capped panel |
| Filter / search bar card | **Auto** |
| CTA / summary strip | **Auto** |

## Future cards

New cards inherit correct behavior by default:

1. Use `SectionCard` or `GlassCard` without extra props → auto height.
2. Add `equalHeight` only for intentional KPI/metric rows with `cardSizing.gridEqual` on the parent.
3. Add `scrollBody` / `scrollable` / scroll utilities only for long or dynamic content.

No page-specific height hacks are required.

## Hover

See [CARD_HOVER.md](./CARD_HOVER.md). `GlassCard` and `SectionCard` enable passive hover by default.

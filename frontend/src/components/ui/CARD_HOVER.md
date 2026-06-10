# Card Hover Standard

Enterprise hover feedback for SensoVibe dashboard surfaces.

## Tokens (`src/lib/card-hover.ts`)

| Token | Class | Cursor | Use |
|-------|-------|--------|-----|
| `passive` | `card-hover` | `default` | KPI cards, section cards, table/filter containers, panels |
| `interactive` | `card-hover-interactive` | `pointer` | Upload zones, clickable widgets |
| `panel` | `panel-hover` | `default` | White bordered panels (no gradient ring) |
| `upload` | `card-hover-upload` | `pointer` | Dashed file-upload areas |

## Hover effects (all variants)

- Background → light warm grey (`--surface`)
- Orange gradient border → slightly stronger (`::after` opacity)
- Shadow → soft depth increase
- Lift → `translateY(-2px)` max
- Duration → 220ms ease
- `prefers-reduced-motion` → no lift; background/shadow/border still transition

## Shared components (automatic inheritance)

| Component | Default hover | Cursor |
|-----------|---------------|--------|
| `GlassCard` | `hover={true}` → passive | `default` |
| `GlassCard` | `interactive={true}` | `pointer` |
| `SectionCard` | `hover={true}` → passive | `default` |
| `SectionCard` | `interactive={true}` | `pointer` |

Disable: `<GlassCard hover={false}>` or `<SectionCard hover={false}>`

## When to use each mode

| Surface | Mode |
|---------|------|
| KPI / dashboard stat cards | `passive` (via `GlassCard`) |
| Search / filter card | `passive` |
| Table container | `passive` |
| Form section cards | `passive` |
| Equipment / review cards | `passive` |
| Asset preview panel | `passive` |
| Upload drop zone | `upload` or `interactive` |
| Clickable dashboard widget | `interactive` |
| Page hero / static headers | **no hover** |

## Future cards

Use `GlassCard` or `SectionCard` — hover is on by default. No page-specific CSS required.

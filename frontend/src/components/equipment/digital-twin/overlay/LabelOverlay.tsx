import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  DEFAULT_LABEL_GAP,
  layoutLabelRow,
  leaderPath,
  shouldUseCompactLabels,
  type LabelItem,
} from "@/lib/digital-twin/label-layout";
import type { SensorStatus } from "@/lib/digital-twin/types";
import { cn } from "@/lib/utils";

/** One chip's content and identity. Positions are supplied per frame. */
export interface OverlayItem {
  id: string;
  /** Lead text: "CH3" for a sensor, "Fan DE" for a bearing. */
  primary: string;
  /** Supporting text: the axis, or the bearing's part number. */
  secondary: string;
  /**
   * What the chip shows below the compact breakpoint — "CH1", "B3".
   *
   * Four bearing chips reading "Motor NDE" need ~330px of row on their own,
   * which does not exist on a phone. A short id always fits.
   */
  compactText: string;
  row: "sensor" | "bearing";
  status?: SensorStatus;
  /** Bearings the form has not filled in, drawn muted. */
  muted?: boolean;
}

export interface AnchorProjection {
  x: number;
  y: number;
  /** Behind the camera or outside the stage — chip and leader are hidden. */
  visible: boolean;
  /** Solid geometry between the camera and the anchor: leader goes dashed. */
  occluded: boolean;
}

export interface LabelOverlayHandle {
  /**
   * Position every chip for this frame.
   *
   * Returns true when at least one chip could not be measured yet — a chip
   * mounted this frame can report a zero width before styles land. The caller
   * must schedule another frame in that case, because the render loop is gated
   * and would otherwise stop with those chips left hidden forever.
   */
  update(frame: {
    positions: Map<string, AnchorProjection>;
    stageWidth: number;
    stageHeight: number;
  }): boolean;
  /** Force a re-measure of chip widths — after a font load or a text change. */
  invalidateSizes(): void;
}

interface LabelOverlayProps {
  items: OverlayItem[];
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onSelect: (id: string) => void;
  /**
   * Ask for another frame. Needed because the render loop is gated: when the
   * chips' own text changes, nothing else is moving, so without this there is
   * no frame in which to re-measure them.
   */
  onRelayout?: () => void;
}

/** Vertical inset of each chip row from the top/bottom of the stage. */
const ROW_INSET = 10;
/** Straight run out of the chip before the leader line kinks. */
const KNEE = 16;
/** Chip widths are re-measured at least this often. */
const REMEASURE_MS = 500;

const STATUS_COLOR: Record<SensorStatus, string> = {
  ok: "#16a34a",
  alert: "#F5A623",
  danger: "#EF4444",
};

/**
 * The label layer: HTML chips in a div, leader lines in an SVG, both sitting
 * over the canvas.
 *
 * Chips are plain DOM rather than sprites or CSS2DRenderer so they get real
 * text rendering, real focus rings and real keyboard activation. React renders
 * the chip *elements*; the per-frame positioning is done imperatively through
 * the handle below, because re-rendering a dozen components at 60fps to move
 * them a few pixels is exactly the kind of work that makes a viewer feel slow.
 */
export const LabelOverlay = forwardRef<LabelOverlayHandle, LabelOverlayProps>(
  function LabelOverlay({ items, highlightedId, onHighlight, onSelect, onRelayout }, ref) {
    const chipRefs = useRef(new Map<string, HTMLButtonElement>());
    const pathRefs = useRef(new Map<string, SVGPathElement>());
    const dotRefs = useRef(new Map<string, SVGCircleElement>());
    const sizes = useRef(new Map<string, { width: number; height: number }>());
    const lastMeasured = useRef(0);
    // State, not a ref: this decides what the chips *render*, so it has to go
    // through React. Kept in a ref too, because `update()` runs inside the
    // render loop and needs the current value without waiting for a commit.
    const [compact, setCompact] = useState(false);
    const compactRef = useRef(compact);
    compactRef.current = compact;

    const setChip = useCallback((id: string, node: HTMLButtonElement | null) => {
      if (node) chipRefs.current.set(id, node);
      else chipRefs.current.delete(id);
    }, []);

    const setPath = useCallback((id: string, node: SVGPathElement | null) => {
      if (node) pathRefs.current.set(id, node);
      else pathRefs.current.delete(id);
    }, []);

    const setDot = useCallback((id: string, node: SVGCircleElement | null) => {
      if (node) dotRefs.current.set(id, node);
      else dotRefs.current.delete(id);
    }, []);

    // Re-measure once the new text is actually on screen.
    //
    // `update()` runs inside the render loop, so the frame right after it flips
    // `compact` still sees the *old* text — measuring there caches the wide
    // widths and the row then cannot be made to fit. Doing it in an effect
    // guarantees React has committed first.
    useEffect(() => {
      sizes.current.clear();
      lastMeasured.current = 0;
      onRelayout?.();
    }, [compact, items, onRelayout]);

    useImperativeHandle(
      ref,
      () => ({
        invalidateSizes: () => {
          sizes.current.clear();
          lastMeasured.current = 0;
        },

        update({ positions, stageWidth, stageHeight }): boolean {
          let unmeasured = false;
          const useCompact = shouldUseCompactLabels(stageWidth);
          if (useCompact !== compactRef.current) {
            compactRef.current = useCompact;
            setCompact(useCompact);
            // Text is about to change, so every cached width is now wrong.
            sizes.current.clear();
            lastMeasured.current = 0;
            // The new text has not been committed yet; ask for another frame.
            unmeasured = true;
          }

          const now = performance.now();
          // Never trust a cached width for long: web fonts land late, and a
          // zoom or a language change resizes every chip underneath us.
          const remeasure = now - lastMeasured.current > REMEASURE_MS;
          if (remeasure) lastMeasured.current = now;

          const rows: Record<"sensor" | "bearing", LabelItem[]> = {
            sensor: [],
            bearing: [],
          };
          const hidden = new Set<string>();

          items.forEach((item) => {
            const chip = chipRefs.current.get(item.id);
            const projection = positions.get(item.id);
            if (!chip) {
              // The element has not attached its ref yet — this happens on the
              // frame the overlay remounts, e.g. switching Labels back on.
              // Without flagging it the gated loop would stop here and leave
              // every chip hidden until some unrelated interaction woke it.
              unmeasured = true;
              return;
            }

            if (!projection || !projection.visible) {
              hidden.add(item.id);
              return;
            }

            let size = sizes.current.get(item.id);
            if (!size || remeasure) {
              const rect = chip.getBoundingClientRect();
              // A chip mid-transition can measure 0; keep the last good value.
              if (rect.width > 0) {
                size = { width: rect.width, height: rect.height };
                sizes.current.set(item.id, size);
              }
            }
            if (!size) {
              unmeasured = true;
              return;
            }

            rows[item.row].push({
              id: item.id,
              anchorX: projection.x,
              anchorY: projection.y,
              width: size.width,
            });
          });

          (["sensor", "bearing"] as const).forEach((row) => {
            const placed = layoutLabelRow(rows[row], {
              stageWidth,
              gap: DEFAULT_LABEL_GAP,
            });

            placed.forEach((chipPlacement) => {
              const chip = chipRefs.current.get(chipPlacement.id);
              const path = pathRefs.current.get(chipPlacement.id);
              const size = sizes.current.get(chipPlacement.id);
              if (!chip || !size) return;

              const top =
                row === "sensor" ? ROW_INSET : stageHeight - ROW_INSET - size.height;
              chip.style.transform = `translate3d(${chipPlacement.x}px, ${top}px, 0)`;
              chip.style.visibility = "visible";

              if (!path) return;
              const centreX = chipPlacement.x + size.width / 2;
              const edgeY = row === "sensor" ? top + size.height : top;
              const kneeY = row === "sensor" ? edgeY + KNEE : edgeY - KNEE;
              path.setAttribute(
                "d",
                leaderPath(centreX, edgeY, chipPlacement.anchorX, chipPlacement.anchorY, kneeY)
              );
              path.style.visibility = "visible";

              const occluded = positions.get(chipPlacement.id)?.occluded ?? false;
              // Dashed means "this anchor is behind something solid" — the
              // operator can see the label refers to a hidden point.
              path.setAttribute("stroke-dasharray", occluded ? "3 4" : "");

              // A dot where the leader meets the machine: without it the line
              // stops in mid-air and the label looks unattached.
              const dot = dotRefs.current.get(chipPlacement.id);
              if (dot) {
                dot.setAttribute("cx", String(chipPlacement.anchorX));
                dot.setAttribute("cy", String(chipPlacement.anchorY));
                dot.style.visibility = "visible";
              }
            });
          });

          hidden.forEach((id) => {
            const chip = chipRefs.current.get(id);
            const path = pathRefs.current.get(id);
            const dot = dotRefs.current.get(id);
            if (chip) chip.style.visibility = "hidden";
            if (path) path.style.visibility = "hidden";
            if (dot) dot.style.visibility = "hidden";
          });

          return unmeasured;
        },
      }),
      [items]
    );

    return (
      <>
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
          aria-hidden
        >
          {items.map((item) => {
            const active = highlightedId === item.id;
            // Leaders are connective tissue, not content: they sit well back
            // until the item is highlighted, so six of them do not compete with
            // the machine for attention.
            const stroke = active ? "#FF6B00" : item.muted ? "#B9C3D1" : "#96A3B4";
            return (
              <g key={item.id} style={{ opacity: active ? 1 : 0.55 }}>
                <path
                  ref={(node) => setPath(item.id, node)}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={active ? 1.6 : 1}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ visibility: "hidden" }}
                />
                <circle
                  ref={(node) => setDot(item.id, node)}
                  r={active ? 3.2 : 2.2}
                  fill={stroke}
                  style={{ visibility: "hidden" }}
                />
              </g>
            );
          })}
        </svg>

        <div className="pointer-events-none absolute inset-0">
          {items.map((item) => {
            const active = highlightedId === item.id;
            const accent = item.status ? STATUS_COLOR[item.status] : "#FF6B00";
            return (
              <button
                key={item.id}
                ref={(node) => setChip(item.id, node)}
                type="button"
                onMouseEnter={() => onHighlight(item.id)}
                onMouseLeave={() => onHighlight(null)}
                onFocus={() => onHighlight(item.id)}
                onBlur={() => onHighlight(null)}
                onClick={() => onSelect(item.id)}
                className={cn(
                  "pointer-events-auto absolute left-0 top-0 whitespace-nowrap rounded-full border",
                  "px-2 py-[3px] text-[11px] font-semibold leading-tight tabular-nums",
                  "transition-[background-color,border-color,box-shadow,color] duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60",
                  active ? "shadow-md" : "shadow-sm"
                )}
                style={{
                  visibility: "hidden",
                  willChange: "transform",
                  backgroundColor: active ? accent : "var(--twin-chip-bg)",
                  borderColor: active ? accent : item.muted ? "var(--twin-chip-muted-border)" : accent,
                  color: active ? "#fff" : "var(--twin-chip-fg)",
                }}
              >
                {/* Sensors stack the axis under the channel; bearings read
                    inline. Below the compact breakpoint only the lead text
                    survives, which is what keeps six chips inside a phone. */}
                <span className={cn("flex", item.row === "sensor" ? "flex-col items-center" : "items-baseline gap-1.5")}>
                  <span style={{ color: active ? "#fff" : accent }}>
                    {compact ? item.compactText : item.primary}
                  </span>
                  {!compact && item.secondary && (
                    <span
                      className={cn("font-medium", item.row === "sensor" && "text-[10px] leading-tight")}
                      style={{ color: active ? "rgba(255,255,255,0.85)" : "var(--twin-chip-muted-fg)" }}
                    >
                      {item.secondary}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </>
    );
  }
);

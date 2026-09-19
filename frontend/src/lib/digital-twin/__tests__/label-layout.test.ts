import { describe, expect, it } from "vitest";
import {
  DEFAULT_LABEL_GAP,
  DEFAULT_LABEL_PADDING,
  layoutLabelRow,
  leaderPath,
  shouldUseCompactLabels,
  type LabelItem,
  type PlacedLabel,
} from "../label-layout";

/** Every adjacent pair, in visual (left-to-right) order. */
function inVisualOrder(placed: PlacedLabel[]): PlacedLabel[] {
  return [...placed].sort((a, b) => a.x - b.x);
}

function assertNoOverlap(placed: PlacedLabel[], gap = DEFAULT_LABEL_GAP) {
  const row = inVisualOrder(placed);
  for (let i = 1; i < row.length; i += 1) {
    const previous = row[i - 1];
    const gapBetween = row[i].x - (previous.x + previous.width);
    // Floating point: allow a hair under the requested gap, never an overlap.
    expect(gapBetween).toBeGreaterThanOrEqual(gap - 1e-6);
  }
}

function item(id: string, anchorX: number, width = 44, anchorY = 100): LabelItem {
  return { id, anchorX, anchorY, width };
}

/** Six sensors bunched onto two bearing housings — the realistic worst case. */
function sixSensors(spread: number, width: number): LabelItem[] {
  return [
    item("CH1", spread * 0.34, width),
    item("CH2", spread * 0.34, width),
    item("CH3", spread * 0.36, width),
    item("CH4", spread * 0.58, width),
    item("CH5", spread * 0.58, width),
    item("CH6", spread * 0.6, width),
  ];
}

describe("layoutLabelRow", () => {
  it("returns nothing for an empty row", () => {
    expect(layoutLabelRow([], { stageWidth: 1024 })).toEqual([]);
  });

  it("leaves a single chip centred on its anchor", () => {
    const [placed] = layoutLabelRow([item("CH1", 500, 60)], { stageWidth: 1024 });
    expect(placed.x + placed.width / 2).toBeCloseTo(500);
  });

  it("does not move chips that already clear each other", () => {
    const placed = layoutLabelRow(
      [item("CH1", 200, 40), item("CH2", 500, 40), item("CH3", 800, 40)],
      { stageWidth: 1024 }
    );
    placed.forEach((chip) => {
      expect(chip.x + chip.width / 2).toBeCloseTo(chip.anchorX);
    });
  });

  it("separates chips sharing one anchor", () => {
    const placed = layoutLabelRow(
      [item("CH1", 400, 50), item("CH2", 400, 50), item("CH3", 400, 50)],
      { stageWidth: 1024 }
    );
    assertNoOverlap(placed);
  });

  // The headline acceptance criterion.
  describe.each([400, 640, 1024, 1920])("at %ipx stage width", (stageWidth) => {
    // Chips are narrower below the compact breakpoint, as the overlay renders
    // id-only labels there.
    const width = shouldUseCompactLabels(stageWidth) ? 38 : 92;

    it("never overlaps six sensor chips", () => {
      assertNoOverlap(layoutLabelRow(sixSensors(stageWidth, width), { stageWidth }));
    });

    it("never overlaps four bearing chips", () => {
      const bearings = [
        item("BRG_MOTOR_DE", stageWidth * 0.28, width),
        item("BRG_MOTOR_NDE", stageWidth * 0.12, width),
        item("BRG_FAN_DE", stageWidth * 0.56, width),
        item("BRG_FAN_NDE", stageWidth * 0.62, width),
      ];
      assertNoOverlap(layoutLabelRow(bearings, { stageWidth }));
    });

    it("keeps chips inside the stage when the row fits", () => {
      const placed = layoutLabelRow(sixSensors(stageWidth, width), { stageWidth });
      const total = placed.length * width + (placed.length - 1) * DEFAULT_LABEL_GAP;
      if (total <= stageWidth - DEFAULT_LABEL_PADDING * 2) {
        placed.forEach((chip) => {
          expect(chip.x).toBeGreaterThanOrEqual(DEFAULT_LABEL_PADDING - 1e-6);
          expect(chip.x + chip.width).toBeLessThanOrEqual(
            stageWidth - DEFAULT_LABEL_PADDING + 1e-6
          );
        });
      }
    });

    it("holds every anchor position from a full turn of the camera", () => {
      // Anchors sweep as the model is orbited; the invariant must survive all
      // of it, including anchors projected off-stage or behind each other.
      for (let step = 0; step < 72; step += 1) {
        const phase = (step / 72) * Math.PI * 2;
        const items = Array.from({ length: 6 }, (_, i) =>
          item(
            `CH${i + 1}`,
            stageWidth / 2 + Math.sin(phase + i * 0.35) * stageWidth * 0.75,
            width
          )
        );
        assertNoOverlap(layoutLabelRow(items, { stageWidth }));
      }
    });
  });

  it("clamps a row that drifts off the right edge", () => {
    const placed = layoutLabelRow(
      [item("CH1", 980, 80), item("CH2", 1000, 80), item("CH3", 1020, 80)],
      { stageWidth: 1024 }
    );
    assertNoOverlap(placed);
    const rightmost = Math.max(...placed.map((chip) => chip.x + chip.width));
    expect(rightmost).toBeLessThanOrEqual(1024 - DEFAULT_LABEL_PADDING + 1e-6);
  });

  it("clamps a row that drifts off the left edge", () => {
    const placed = layoutLabelRow(
      [item("CH1", -40, 80), item("CH2", 10, 80), item("CH3", 30, 80)],
      { stageWidth: 1024 }
    );
    assertNoOverlap(placed);
    expect(Math.min(...placed.map((chip) => chip.x))).toBeGreaterThanOrEqual(
      DEFAULT_LABEL_PADDING - 1e-6
    );
  });

  it("still refuses to overlap when the row cannot possibly fit", () => {
    // Eight 90px chips need 776px of gap-inclusive width in a 300px stage.
    const items = Array.from({ length: 8 }, (_, i) => item(`CH${i + 1}`, 150, 90));
    assertNoOverlap(layoutLabelRow(items, { stageWidth: 300 }));
  });

  it("orders chips left to right by anchor, whatever the input order", () => {
    const anchors = [item("CH3", 700), item("CH1", 200), item("CH2", 450)];
    const placed = layoutLabelRow(anchors, { stageWidth: 1024 });
    expect(inVisualOrder(placed).map((chip) => chip.id)).toEqual(["CH1", "CH2", "CH3"]);
  });

  it("returns results in input order so DOM order stays stable", () => {
    const anchors = [item("CH3", 700), item("CH1", 200), item("CH2", 450)];
    expect(layoutLabelRow(anchors, { stageWidth: 1024 }).map((c) => c.id)).toEqual([
      "CH3",
      "CH1",
      "CH2",
    ]);
  });

  it("keeps a stable order when two anchors coincide", () => {
    // Ties break on id, so a chip cannot swap sides with its neighbour between
    // frames and make the leader lines flick across each other.
    const a = layoutLabelRow([item("CH2", 400), item("CH1", 400)], { stageWidth: 1024 });
    const b = layoutLabelRow([item("CH1", 400), item("CH2", 400)], { stageWidth: 1024 });
    const orderOf = (placed: PlacedLabel[]) => inVisualOrder(placed).map((c) => c.id);
    expect(orderOf(a)).toEqual(["CH1", "CH2"]);
    expect(orderOf(b)).toEqual(["CH1", "CH2"]);
  });

  it("moves chips continuously as an anchor moves, with no jumps", () => {
    let previous: number | null = null;
    for (let anchorX = 300; anchorX <= 500; anchorX += 2) {
      const [, moving] = layoutLabelRow(
        [item("CH1", 280, 60), item("CH2", anchorX, 60)],
        { stageWidth: 1024 }
      );
      if (previous !== null) expect(Math.abs(moving.x - previous)).toBeLessThanOrEqual(2.001);
      previous = moving.x;
    }
  });

  it("honours a custom gap and padding", () => {
    const placed = layoutLabelRow(sixSensors(1024, 92), {
      stageWidth: 1024,
      gap: 20,
      padding: 32,
    });
    assertNoOverlap(placed, 20);
  });

  it("preserves each chip's anchor for the leader line", () => {
    const anchors = [item("CH1", 200, 44, 120), item("CH2", 210, 44, 90)];
    const placed = layoutLabelRow(anchors, { stageWidth: 1024 });
    expect(placed.map((c) => [c.anchorX, c.anchorY])).toEqual([
      [200, 120],
      [210, 90],
    ]);
  });
});

describe("shouldUseCompactLabels", () => {
  it("is compact below 640px and full at or above it", () => {
    expect(shouldUseCompactLabels(400)).toBe(true);
    expect(shouldUseCompactLabels(639)).toBe(true);
    expect(shouldUseCompactLabels(640)).toBe(false);
    expect(shouldUseCompactLabels(1920)).toBe(false);
  });
});

describe("leaderPath", () => {
  it("goes straight out of the chip, knees, then meets the anchor", () => {
    expect(leaderPath(100, 40, 260, 180, 90)).toBe("M 100 40 L 100 90 L 260 180");
  });
});

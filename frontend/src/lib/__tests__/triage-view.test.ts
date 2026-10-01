import { describe, expect, it } from "vitest";

import {
  BAND_CHIP,
  BAND_LABEL,
  BAND_TONE,
  ageText,
  directionLabel,
  directionTone,
  feedbackBlockedReason,
  groupByMachine,
  hasGaps,
  headline,
  needsCorrection,
  needsNote,
  ownerText,
  priorityText,
  statusLabel,
  urgencyLabel,
} from "@/lib/triage-view";
import type { PriorityBand, QueueItem } from "@/types/triage";

/**
 * The priority queue's view logic — sections 15.2, 16.1 and 20.
 *
 * Almost every test here is about the same thing: a value the platform
 * could not work out has to reach the screen as a sentence, never as a
 * blank or a zero. A blank cell reads as "fine" and a zero reads as "none",
 * and on this platform both are usually the opposite of the truth.
 */

function item(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    rank: 1,
    finding_id: "f-1",
    machine_name: "Cooling Water Pump 1",
    sensor_id: "s-1",
    channel: 0,
    fault_suspected: "Outer race defect",
    fault_key: "bearing_outer_race",
    family: "Rolling-element bearing",
    severity: 4,
    stage: "severe",
    confidence: 0.86,
    recommended_action: "Plan bearing replacement.",
    urgency: "plan_maintenance",
    shutdown_advised: false,
    first_detected_at: "2026-09-01T00:00:00Z",
    days_since_detected: 27,
    trend_direction: "rising",
    assigned_analyst: null,
    status: "new",
    priority_score: 66.6,
    priority_band: "high",
    priority_reason: "Priority 67 of 100 (high).",
    unknowns: [],
    latest_feedback: null,
    suppressed: false,
    ...overrides,
  };
}

describe("a value that could not be worked out becomes words", () => {
  it("says a finding could not be ranked rather than showing nothing", () => {
    expect(priorityText(item({ priority_score: null }))).toBe(
      "Could not be ranked",
    );
  });

  it("does not render an unranked finding as zero", () => {
    expect(priorityText(item({ priority_score: null }))).not.toContain("0");
  });

  it("says when a first sighting was never recorded", () => {
    expect(ageText(item({ days_since_detected: null }))).toBe(
      "First sighting not recorded",
    );
  });

  it("says nobody is assigned rather than leaving the owner blank", () => {
    expect(ownerText(item({ assigned_analyst: null }))).toBe(
      "Nobody assigned",
    );
    expect(ownerText(item({ assigned_analyst: "a.kulkarni" }))).toBe(
      "a.kulkarni",
    );
  });

  it("distinguishes an unknown trend from a steady one", () => {
    expect(directionLabel("unknown")).toBe("Not enough readings");
    expect(directionLabel("steady")).toBe("Holding steady");
    expect(directionLabel("unknown")).not.toBe(directionLabel("steady"));
  });

  it("gives an unknown trend its own colour, not the steady one", () => {
    expect(directionTone("unknown")).not.toBe(directionTone("steady"));
  });
});

describe("the queue's own words", () => {
  it("counts days rather than showing a raw timestamp", () => {
    expect(ageText(item({ days_since_detected: 27 }))).toBe(
      "Developing for 27 days",
    );
    expect(ageText(item({ days_since_detected: 0 }))).toBe("First seen today");
    expect(ageText(item({ days_since_detected: 1 }))).toBe(
      "First seen yesterday",
    );
  });

  it("says outright when stopping the machine is on the table", () => {
    const line = headline(item({ shutdown_advised: true }));
    expect(line).toContain("stopping the machine");
  });

  it("leads with the mute when a finding is muted", () => {
    expect(headline(item({ suppressed: true }))).toContain("Muted");
  });

  it("writes a muted finding's priority as muted, not as a number", () => {
    expect(priorityText(item({ suppressed: true, priority_score: 61.7 }))).toBe(
      "Muted by an analyst",
    );
  });

  it("turns every band and status into plain words", () => {
    const bands: PriorityBand[] = [
      "immediate",
      "high",
      "medium",
      "low",
      "watch",
      "suppressed",
      "unknown",
    ];
    for (const band of bands) {
      expect(BAND_LABEL[band]).toBeTruthy();
      expect(BAND_TONE[band]).toBeTruthy();
      expect(BAND_CHIP[band]).toBeTruthy();
    }
    expect(statusLabel("awaiting_shutdown")).toBe("Awaiting shutdown");
    expect(urgencyLabel("inspect_when_convenient")).toBe(
      "Look when convenient",
    );
  });
});

describe("gaps in the evidence are surfaced, not folded in", () => {
  it("flags a ranking that was computed with inputs missing", () => {
    expect(hasGaps(item({ unknowns: [] }))).toBe(false);
    expect(hasGaps(item({ unknowns: ["Safety impact is not recorded."] }))).toBe(
      true,
    );
  });
});

describe("feedback cannot be submitted half-finished", () => {
  it("asks for a verdict first", () => {
    expect(feedbackBlockedReason(null, "", "")).toBe("Choose what you found.");
  });

  it("refuses to mute a fault without a reason", () => {
    const blocked = feedbackBlockedReason("ignore_for_machine", "  ", "");
    expect(blocked).toContain("needs a reason");
    expect(feedbackBlockedReason("ignore_for_machine", "pipe resonance", ""))
      .toBeNull();
  });

  it("refuses a correction that does not say what the fault was", () => {
    const blocked = feedbackBlockedReason("wrong_fault_type", "", "");
    expect(blocked).toContain("what the fault actually was");
    expect(
      feedbackBlockedReason("wrong_fault_type", "", "bearing_inner_race"),
    ).toBeNull();
  });

  it("lets an ordinary verdict through with nothing else filled in", () => {
    expect(feedbackBlockedReason("correct_detection", "", "")).toBeNull();
    expect(feedbackBlockedReason("false_alarm", "", "")).toBeNull();
  });

  it("agrees with the backend about which verdicts need what", () => {
    expect(needsNote("ignore_for_machine")).toBe(true);
    expect(needsNote("false_alarm")).toBe(false);
    expect(needsCorrection("wrong_fault_type")).toBe(true);
    expect(needsCorrection("new_fault_label")).toBe(true);
    expect(needsCorrection("correct_detection")).toBe(false);
  });
});

describe("grouping", () => {
  it("keeps rank order inside each machine", () => {
    const groups = groupByMachine([
      item({ rank: 1, machine_name: "P-101" }),
      item({ rank: 2, machine_name: "P-204" }),
      item({ rank: 3, machine_name: "P-101" }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0].machine).toBe("P-101");
    expect(groups[0].items.map((row) => row.rank)).toEqual([1, 3]);
  });

  it("names a machine with no name rather than dropping the row", () => {
    const groups = groupByMachine([item({ machine_name: null })]);
    expect(groups[0].machine).toBe("Unnamed machine");
    expect(groups[0].items).toHaveLength(1);
  });
});

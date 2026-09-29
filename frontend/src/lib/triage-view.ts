import type {
  FeedbackVerdict,
  PriorityBand,
  QueueItem,
  TrendDirection,
  TriageStatus,
  Urgency,
} from "@/types/triage";

/**
 * Turning Phase 3 and Phase 4 into words and colours — the decisions worth
 * testing, kept out of the component so they can be.
 *
 * One rule runs through all of it: **a value the platform could not work
 * out is rendered as a sentence, never as a blank or a zero.** A blank cell
 * reads as "fine" and a zero reads as "none", and on this platform both are
 * usually wrong. `priority_score: null` means nobody could rank it;
 * `days_since_detected: null` means the first sighting was not recorded.
 * Each gets words.
 */

/** Severity colours, from the app's own tokens. Light theme throughout. */
export const BAND_TONE: Record<PriorityBand, string> = {
  immediate: "text-machine-critical",
  high: "text-machine-critical",
  medium: "text-machine-warning",
  low: "text-muted-foreground",
  watch: "text-muted-foreground",
  suppressed: "text-helper",
  unknown: "text-helper",
};

export const BAND_CHIP: Record<PriorityBand, string> = {
  immediate: "bg-machine-critical/10 border-machine-critical text-machine-critical",
  high: "bg-machine-critical/10 border-machine-critical text-machine-critical",
  medium: "bg-machine-warning/10 border-machine-warning text-machine-warning",
  // Neutral surfaces, not `bg-signal-light`. That token is #F5A623, a
  // saturated amber meant for focus rings and highlights; using it as a
  // panel background made an ordinary "low priority" chip shout louder
  // than the critical one above it, and put muted text on amber.
  low: "bg-surface border-border text-muted-foreground",
  watch: "bg-surface border-border text-muted-foreground",
  suppressed: "bg-muted border-border text-helper",
  unknown: "bg-muted border-border text-helper",
};

/** Plain words for section 15.2's priority band. */
export const BAND_LABEL: Record<PriorityBand, string> = {
  immediate: "Immediate",
  high: "High",
  medium: "Medium",
  low: "Low",
  watch: "Watch",
  suppressed: "Muted",
  unknown: "Not ranked",
};

const URGENCY_LABEL: Record<Urgency, string> = {
  none: "No action",
  monitor: "Keep watching",
  inspect_when_convenient: "Look when convenient",
  inspect_soon: "Inspect at next opportunity",
  plan_maintenance: "Plan maintenance",
  immediate: "Act now",
};

const STATUS_LABEL: Record<TriageStatus, string> = {
  new: "New",
  assigned: "Assigned",
  investigating: "Investigating",
  awaiting_shutdown: "Awaiting shutdown",
  resolved: "Resolved",
  closed: "Closed",
};

const DIRECTION_LABEL: Record<TrendDirection, string> = {
  rising: "Getting worse",
  steady: "Holding steady",
  falling: "Recovering",
  unknown: "Not enough readings",
};

export function urgencyLabel(urgency: Urgency): string {
  return URGENCY_LABEL[urgency] ?? urgency;
}

/**
 * The fault stage in words.
 *
 * The engine's stages are snake_case identifiers and one of them,
 * `early_fault_suspected`, is long enough that it reached the screen
 * verbatim and looked like a bug. Anything not listed is de-underscored
 * rather than shown raw.
 */
export function stageLabel(stage: string): string {
  const known: Record<string, string> = {
    normal: "Normal",
    watch: "Watch",
    early_fault_suspected: "Early fault suspected",
    developing: "Developing",
    severe: "Severe",
    critical: "Critical",
  };
  return known[stage] ?? stage.replace(/_/g, " ");
}

export function statusLabel(status: TriageStatus): string {
  return STATUS_LABEL[status] ?? status;
}

/**
 * Words for the trend, including the one that matters most.
 *
 * "unknown" is not "steady". A finding seen twice has a direction and it is
 * noise half the time, so the platform refuses to call it — and the screen
 * has to repeat that refusal rather than showing a flat line.
 */
export function directionLabel(direction: TrendDirection): string {
  return DIRECTION_LABEL[direction] ?? direction;
}

export function directionTone(direction: TrendDirection): string {
  if (direction === "rising") return "text-machine-critical";
  if (direction === "falling") return "text-brand";
  if (direction === "unknown") return "text-helper";
  return "text-muted-foreground";
}

/** How a priority score is written. Null becomes words, never a dash. */
export function priorityText(item: QueueItem): string {
  if (item.suppressed) return "Muted by an analyst";
  if (item.priority_score === null) return "Could not be ranked";
  return `${Math.round(item.priority_score)} / 100`;
}

/**
 * How long this has been known about. Section 15.2 asks for "time since
 * first detected", and the honest answer is sometimes that nobody recorded
 * a first sighting.
 */
export function ageText(item: QueueItem): string {
  if (item.days_since_detected === null) return "First sighting not recorded";
  if (item.days_since_detected === 0) return "First seen today";
  if (item.days_since_detected === 1) return "First seen yesterday";
  return `Developing for ${item.days_since_detected} days`;
}

/** Who is on it. An unassigned finding says so rather than showing blank. */
export function ownerText(item: QueueItem): string {
  if (item.assigned_analyst) return item.assigned_analyst;
  return "Nobody assigned";
}

/**
 * The one line that should reach somebody who reads nothing else.
 *
 * A shutdown recommendation is said outright. Anything held back by weak
 * evidence says so in the same breath, because a capped urgency and a mild
 * fault look identical otherwise, and the whole point of capping is that
 * somebody goes and closes the gap.
 */
export function headline(item: QueueItem): string {
  if (item.suppressed) {
    return `Muted: ${item.fault_suspected} on channel ${item.channel}.`;
  }
  if (item.shutdown_advised) {
    return `${item.fault_suspected}: stopping the machine is on the table.`;
  }
  return `${item.fault_suspected} — ${urgencyLabel(item.urgency).toLowerCase()}.`;
}

/**
 * Whether this row needs the "we could not see everything" note.
 *
 * Shown whenever the platform listed inputs it could not obtain. Hiding it
 * would make a ranking computed from half the evidence look like one
 * computed from all of it.
 */
export function hasGaps(item: QueueItem): boolean {
  return item.unknowns.length > 0;
}

/**
 * Verdicts that need a written reason before they can be submitted.
 *
 * Muting is the only feedback option that can hide a real fault, so the
 * backend refuses one without a note. The form enforces the same rule so
 * the analyst finds out before the request, not after it.
 */
export const VERDICTS_NEEDING_NOTE: FeedbackVerdict[] = ["ignore_for_machine"];

/** Verdicts that must name what the fault actually was. */
export const VERDICTS_NEEDING_CORRECTION: FeedbackVerdict[] = [
  "wrong_fault_type",
  "new_fault_label",
];

export function needsNote(verdict: FeedbackVerdict): boolean {
  return VERDICTS_NEEDING_NOTE.includes(verdict);
}

export function needsCorrection(verdict: FeedbackVerdict): boolean {
  return VERDICTS_NEEDING_CORRECTION.includes(verdict);
}

/**
 * Whether this feedback can be submitted yet, and what is missing.
 *
 * Returns the reason rather than a boolean so the button can explain why it
 * is disabled. A greyed-out control with no explanation is a dead end.
 */
export function feedbackBlockedReason(
  verdict: FeedbackVerdict | null,
  note: string,
  correctedFault: string,
): string | null {
  if (!verdict) return "Choose what you found.";
  if (needsNote(verdict) && !note.trim()) {
    return (
      "Muting a fault needs a reason. An unexplained mute is " +
      "indistinguishable from not monitoring the machine."
    );
  }
  if (needsCorrection(verdict) && !correctedFault.trim()) {
    return (
      "Say what the fault actually was. A correction that only says " +
      "“wrong” cannot be learned from."
    );
  }
  return null;
}

/** Group a queue by machine, preserving rank order within each. */
export function groupByMachine(
  items: QueueItem[],
): Array<{ machine: string; items: QueueItem[] }> {
  const groups = new Map<string, QueueItem[]>();
  for (const item of items) {
    const key = item.machine_name ?? "Unnamed machine";
    const existing = groups.get(key);
    if (existing) existing.push(item);
    else groups.set(key, [item]);
  }
  return [...groups.entries()].map(([machine, rows]) => ({
    machine,
    items: rows,
  }));
}

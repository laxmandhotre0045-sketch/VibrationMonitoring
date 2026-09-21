import type { EquipmentHealthStatus } from "@/types/dashboard";

/**
 * One visual language for condition across the AI Analysis page.
 *
 * Three different scales are shown there — the machine grade from the fleet
 * summary, the page's own condition band, and a fault pattern's severity — and
 * a reader should not have to learn three palettes to know which of them is the
 * bad one. They all map onto these five tones.
 *
 * Each tone is a *box*, not a dot: a solid badge carries at a glance in a way a
 * 8px dot never does, and the rail lights the row from its left edge so a
 * flagged branch is findable by colour down the side of a long tree.
 */
export type StatusTone = "critical" | "warning" | "caution" | "healthy" | "neutral";

export interface StatusToneStyle {
  /** Solid badge — the status as a filled box with its own soft drop glow. */
  chip: string;
  /** Left rail: the light source, glowing outward into the row. */
  rail: string;
  /**
   * Wash fading in from the rail. Empty for the tones that need no attention —
   * a tree where every healthy row is also tinted has no signal left to spend.
   */
  wash: string;
  /** For a value or label that should carry the status itself. */
  text: string;
  /** Outline for a panel framed by its status. */
  ring: string;
}

export const STATUS_TONES: Record<StatusTone, StatusToneStyle> = {
  critical: {
    chip: "border-transparent bg-machine-critical text-white shadow-[0_1px_7px_-1px_rgba(239,68,68,0.55)]",
    rail: "bg-machine-critical shadow-[0_0_12px_1px_rgba(239,68,68,0.6)]",
    wash: "bg-gradient-to-r from-machine-critical/10 via-machine-critical/[0.03] to-transparent",
    text: "text-machine-critical",
    ring: "ring-machine-critical/35",
  },
  warning: {
    chip: "border-transparent bg-machine-warning text-white shadow-[0_1px_7px_-1px_rgba(245,166,35,0.55)]",
    rail: "bg-machine-warning shadow-[0_0_12px_1px_rgba(245,166,35,0.6)]",
    wash: "bg-gradient-to-r from-machine-warning/[0.12] via-machine-warning/[0.04] to-transparent",
    text: "text-signal-deep",
    ring: "ring-machine-warning/40",
  },
  caution: {
    chip: "border-transparent bg-brand text-white shadow-[0_1px_7px_-1px_rgba(21,54,109,0.45)]",
    rail: "bg-brand/70 shadow-[0_0_12px_1px_rgba(21,54,109,0.35)]",
    wash: "bg-gradient-to-r from-brand/[0.07] via-brand/[0.02] to-transparent",
    text: "text-brand",
    ring: "ring-brand/30",
  },
  healthy: {
    chip: "border-transparent bg-machine-healthy text-white shadow-[0_1px_7px_-1px_rgba(34,197,94,0.5)]",
    rail: "bg-machine-healthy shadow-[0_0_10px_1px_rgba(34,197,94,0.45)]",
    wash: "",
    text: "text-machine-healthy",
    ring: "ring-machine-healthy/35",
  },
  neutral: {
    chip: "border-transparent bg-machine-offline text-white",
    rail: "bg-machine-offline",
    wash: "",
    text: "text-muted-foreground",
    ring: "ring-border",
  },
};

/**
 * The machine grade from the fleet summary.
 *
 * `no_baseline` is neutral rather than a warning of its own: nothing is wrong
 * with the machine, the limits simply have nothing to compare against yet.
 */
export function toneForHealthStatus(status: EquipmentHealthStatus): StatusTone {
  switch (status) {
    case "critical":
      return "critical";
    case "warning":
      return "warning";
    case "normal":
      return "healthy";
    default:
      return "neutral";
  }
}

export function statusToneStyle(status: EquipmentHealthStatus): StatusToneStyle {
  return STATUS_TONES[toneForHealthStatus(status)];
}

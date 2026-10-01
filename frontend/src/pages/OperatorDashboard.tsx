import { AlertTriangle, CheckCircle2, HelpCircle, Thermometer } from "lucide-react";

import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";
import { useOperatorView } from "@/hooks/useDashboards";
import type { OperatorMachine } from "@/types/dashboards";

/**
 * Section 19.1 — the operator dashboard.
 *
 * This is the one screen in the platform read by somebody standing up. It
 * answers two questions per machine, is it running and is it alright, and
 * gives one sentence to act on. Everything that belongs to an analyst —
 * evidence, orders, confidence — is deliberately absent.
 *
 * **Temperature is shown as unavailable rather than left out.** The
 * requirement asks for it and nothing on this platform measures one. An
 * operator shown five of six fields will assume the sixth was fine, which
 * is exactly the inference this platform exists to prevent.
 */

const TONE: Record<OperatorMachine["status"], string> = {
  attention: "border-machine-critical bg-machine-critical/10",
  watch: "border-machine-warning bg-machine-warning/10",
  ok: "border-border bg-card",
  no_data: "border-border bg-muted",
};

const LABEL: Record<OperatorMachine["status"], string> = {
  attention: "Needs attention",
  watch: "Being watched",
  ok: "Running normally",
  no_data: "Nothing measured",
};

const ICON: Record<OperatorMachine["status"], typeof AlertTriangle> = {
  attention: AlertTriangle,
  watch: AlertTriangle,
  ok: CheckCircle2,
  no_data: HelpCircle,
};

function formatRms(value: number | null): string {
  if (value === null) return "Not measured";
  return `${value.toFixed(4)} g`;
}

function formatSeen(value: string | null): string {
  if (!value) return "Never";
  const hours = (Date.now() - new Date(value).getTime()) / 3_600_000;
  if (hours < 1) return "Minutes ago";
  if (hours < 48) return `${Math.round(hours)} hours ago`;
  return `${Math.round(hours / 24)} days ago`;
}

function MachineCard({ machine }: { machine: OperatorMachine }) {
  const Icon = ICON[machine.status];
  return (
    <GlassCard className={cn("border p-g4", TONE[machine.status])}>
      <div className="flex items-start justify-between gap-g2">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-card-title truncate">
            {machine.machine_name}
          </h3>
          <p className="text-xs text-muted-foreground truncate">
            {[machine.plant_name, machine.area].filter(Boolean).join(" · ")}
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-g1 text-xs font-semibold">
          <Icon className="h-4 w-4" aria-hidden />
          {LABEL[machine.status]}
        </span>
      </div>

      <p className="mt-g3 text-sm font-medium text-foreground">
        {machine.action}
      </p>

      <dl className="mt-g3 grid grid-cols-2 gap-g2 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-helper">
            Running state
          </dt>
          <dd className="text-foreground">
            {machine.running_state === "unknown"
              ? "Not known"
              : machine.running_state.replace(/_/g, " ")}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-helper">
            Vibration level
          </dt>
          <dd className="text-foreground tabular-nums">
            {formatRms(machine.rms_g)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-helper">
            Alarms
          </dt>
          <dd className="text-foreground">
            {machine.alarms === 0
              ? "None"
              : `${machine.alarms}${
                  machine.worst_alarm_band
                    ? ` (worst: ${machine.worst_alarm_band})`
                    : ""
                }`}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-helper">
            Last reading
          </dt>
          <dd className="text-foreground">{formatSeen(machine.last_seen)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="flex items-center gap-g1 text-xs uppercase tracking-wide text-helper">
            <Thermometer className="h-3.5 w-3.5" aria-hidden />
            Temperature
          </dt>
          {/*
            Shown, and shown as unavailable. Leaving the field off would let
            an operator assume it was checked and was fine.
          */}
          <dd className="text-helper italic">{machine.temperature_note}</dd>
        </div>
      </dl>
    </GlassCard>
  );
}

export function OperatorDashboard() {
  const { data, machines, isLoading, isError } = useOperatorView();

  return (
    <div className="space-y-g4">
      <PageHero
        title="Operator view"
        subtitle="Is each machine running, and is it alright. One sentence to act on, and nothing that needs an analyst to interpret."
      />

      {data ? (
        <div className="flex flex-wrap gap-g3 text-sm">
          <span className="font-semibold text-machine-critical">
            {data.counts.attention} need attention
          </span>
          <span className="text-machine-warning">
            {data.counts.watch} being watched
          </span>
          <span className="text-muted-foreground">
            {data.counts.ok} running normally
          </span>
          <span className="text-helper">
            {data.counts.no_data} with nothing measured
          </span>
        </div>
      ) : null}

      {isLoading ? (
        <GlassCard className="p-g4">
          <p className="text-sm text-muted-foreground">Loading the plant…</p>
        </GlassCard>
      ) : null}

      {isError ? (
        <GlassCard className="p-g4">
          <p className="flex items-start gap-g2 text-sm text-machine-critical">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              The plant could not be loaded. That is not the same as every
              machine being fine — nothing is known right now.
            </span>
          </p>
        </GlassCard>
      ) : null}

      <div className="grid gap-g3 md:grid-cols-2">
        {machines.map((machine) => (
          <MachineCard key={machine.equipment_id} machine={machine} />
        ))}
      </div>

      {data ? (
        <p className="text-xs text-helper">{data.reason}</p>
      ) : null}
    </div>
  );
}

import { Link } from "react-router-dom";
import { AlertTriangle, Info, TrendingDown, TrendingUp } from "lucide-react";

import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";
import { useFleet } from "@/hooks/useDashboards";
import type { FleetMachine } from "@/types/dashboards";

/**
 * Section 19.3 — the management dashboard.
 *
 * Two things shape this screen and both are about not flattering the
 * platform.
 *
 * **Every site figure says what it was computed from.** The averages cover
 * the machines that could be scored; the ones that could not are named
 * underneath rather than quietly counted as healthy. A site health score of
 * 88 computed from nine of twenty machines is not a site health score.
 *
 * **False-alarm rate is allowed to get worse.** It is the share of analyst
 * verdicts that rejected a finding, so it rises when the platform is wrong.
 * A number that only ever improved would make the feedback loop
 * decorative, and this is the screen where that would be least noticed.
 */

function scoreTone(score: number | null): string {
  if (score === null) return "text-helper";
  if (score >= 75) return "text-brand";
  if (score >= 55) return "text-machine-warning";
  return "text-machine-critical";
}

function Metric({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: string;
}) {
  return (
    <GlassCard className="p-g3">
      <p className="text-xs uppercase tracking-wide text-helper">{label}</p>
      <p
        className={cn(
          "mt-g1 text-2xl font-semibold tabular-nums",
          tone ?? "text-card-title",
        )}
      >
        {value}
      </p>
      {note ? (
        <p className="mt-g1 text-xs text-muted-foreground">{note}</p>
      ) : null}
    </GlassCard>
  );
}

function RiskRow({ machine, rank }: { machine: FleetMachine; rank: number }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-g2 pr-g2 text-sm text-muted-foreground tabular-nums">
        {rank}
      </td>
      <td className="py-g2 pr-g2">
        <span className="text-sm font-medium text-foreground">
          {machine.machine_name}
        </span>
        <span className="block text-xs text-muted-foreground">
          {[machine.area, machine.criticality].filter(Boolean).join(" · ")}
        </span>
      </td>
      <td className={cn("py-g2 pr-g2 text-sm tabular-nums",
                        scoreTone(machine.health))}>
        {machine.health === null ? "Not scored" : machine.health}
        {machine.health_ceiling && machine.health_ceiling < 100
          ? ` / ${machine.health_ceiling}`
          : ""}
      </td>
      <td className={cn("py-g2 pr-g2 text-sm tabular-nums",
                        scoreTone(machine.reliability))}>
        {machine.reliability === null ? "No record" : machine.reliability}
        {machine.reliability_proven === false ? " (unproven)" : ""}
      </td>
      <td className="py-g2 text-sm text-muted-foreground tabular-nums">
        {machine.open_findings}
      </td>
    </tr>
  );
}

export function ManagementDashboard() {
  const { data, isLoading, isError } = useFleet();

  return (
    <div className="space-y-g4">
      <PageHero
        title="Management view"
        subtitle="The whole site in one picture — how it is, how dependable it has been, and whether the platform is earning its keep."
      />

      {isLoading ? (
        <GlassCard className="p-g4">
          <p className="text-sm text-muted-foreground">Gathering the site…</p>
        </GlassCard>
      ) : null}

      {isError ? (
        <GlassCard className="p-g4">
          <p className="flex items-start gap-g2 text-sm text-machine-critical">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              The site summary could not be loaded. Nothing is known right
              now, which is not the same as nothing being wrong.
            </span>
          </p>
        </GlassCard>
      ) : null}

      {data ? (
        <>
          <div className="grid gap-g3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Site health"
              value={
                data.site_health_score === null
                  ? "Not known"
                  : `${data.site_health_score}`
              }
              tone={scoreTone(data.site_health_score)}
              note={`Averaged over ${data.counts.scored} of ${data.counts.machines} machines`}
            />
            <Metric
              label="Fleet reliability"
              value={
                data.site_reliability_score === null
                  ? "Not known"
                  : `${data.site_reliability_score}`
              }
              tone={scoreTone(data.site_reliability_score)}
              note="How dependable the records have been"
            />
            <Metric
              label="Critical alarms"
              value={`${data.counts.critical_alarms}`}
              tone={
                data.counts.critical_alarms
                  ? "text-machine-critical"
                  : "text-card-title"
              }
              note={`${data.counts.open_findings} open finding(s)`}
            />
            <Metric
              label="Machines under watch"
              value={`${data.counts.under_watch}`}
              note={`${data.counts.unmeasured} could not be scored at all`}
            />
          </div>

          {data.counts.unmeasured > 0 ? (
            <GlassCard className="border border-border bg-surface p-g3">
              <p className="flex items-start gap-g2 text-sm text-muted-foreground">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-helper" aria-hidden />
                <span>
                  {data.reason}{" "}
                  {data.unmeasured_machines.length ? (
                    <>
                      Excluded from the averages above:{" "}
                      <span className="text-foreground">
                        {data.unmeasured_machines.join(", ")}
                      </span>
                      .
                    </>
                  ) : null}
                </span>
              </p>
            </GlassCard>
          ) : null}

          <GlassCard className="p-g4">
            <h3 className="text-base font-semibold text-card-title">
              Most at risk
            </h3>
            <p className="mt-g1 text-sm text-muted-foreground">
              Worst health first. Machines that could not be scored are not
              ranked here — they are listed above instead, because an
              unmeasured machine is not a low-risk one.
            </p>
            {data.most_at_risk.length ? (
              <div className="mt-g3 overflow-x-auto">
                <table className="w-full min-w-[34rem]">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="pb-g2 pr-g2 text-xs uppercase tracking-wide text-helper">
                        #
                      </th>
                      <th className="pb-g2 pr-g2 text-xs uppercase tracking-wide text-helper">
                        Machine
                      </th>
                      <th className="pb-g2 pr-g2 text-xs uppercase tracking-wide text-helper">
                        Health
                      </th>
                      <th className="pb-g2 pr-g2 text-xs uppercase tracking-wide text-helper">
                        Reliability
                      </th>
                      <th className="pb-g2 text-xs uppercase tracking-wide text-helper">
                        Open
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.most_at_risk.map((machine, index) => (
                      <RiskRow
                        key={machine.equipment_id}
                        machine={machine}
                        rank={index + 1}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-g3 text-sm text-helper">
                No machine on this site could be scored, so nothing can be
                ranked.
              </p>
            )}
          </GlassCard>

          <div className="grid gap-g3 md:grid-cols-2">
            <GlassCard className="p-g4">
              <h3 className="text-base font-semibold text-card-title">
                Is the platform right?
              </h3>
              <p className="mt-g2 flex items-baseline gap-g2">
                <span
                  className={cn(
                    "text-2xl font-semibold tabular-nums",
                    data.feedback.false_alarm_rate === null
                      ? "text-helper"
                      : data.feedback.false_alarm_rate > 0.3
                        ? "text-machine-critical"
                        : "text-brand",
                  )}
                >
                  {data.feedback.false_alarm_rate === null
                    ? "Not known"
                    : `${Math.round(data.feedback.false_alarm_rate * 100)}%`}
                </span>
                <span className="text-sm text-muted-foreground">
                  of judged findings were rejected
                </span>
                {data.feedback.trend === "improving" ? (
                  <TrendingDown className="h-4 w-4 text-brand" aria-hidden />
                ) : data.feedback.trend === "worsening" ? (
                  <TrendingUp className="h-4 w-4 text-machine-critical" aria-hidden />
                ) : null}
              </p>
              <p className="mt-g2 text-sm text-muted-foreground">
                {data.feedback.reason}
              </p>
              <p className="mt-g2 text-xs text-helper">
                This number is allowed to get worse. It rises when the
                platform is wrong, which is what makes it worth reading.
              </p>
            </GlassCard>

            <GlassCard className="p-g4">
              <h3 className="text-base font-semibold text-card-title">
                Maintenance action
              </h3>
              <p className="mt-g2 text-sm text-muted-foreground">
                {data.maintenance.reason}
              </p>
              <dl className="mt-g3 grid grid-cols-2 gap-g2 text-sm">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-helper">
                    Unassigned
                  </dt>
                  <dd className="text-foreground tabular-nums">
                    {data.maintenance.unassigned}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-helper">
                    Repairs confirmed
                  </dt>
                  <dd className="text-foreground tabular-nums">
                    {data.maintenance.repairs_confirmed}
                  </dd>
                </div>
              </dl>
              <Link
                to="/triage"
                className="mt-g3 inline-block text-sm font-medium text-brand underline"
              >
                Open the priority queue
              </Link>
            </GlassCard>
          </div>
        </>
      ) : null}
    </div>
  );
}

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ClipboardList,
  Info,
  Minus,
  ShieldQuestion,
  UserCheck,
} from "lucide-react";

import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";
import {
  useAssignFinding,
  useFeedbackSummary,
  useSubmitFeedback,
  useTriageQueue,
  useVerdicts,
} from "@/hooks/useTriage";
import {
  BAND_CHIP,
  BAND_LABEL,
  ageText,
  directionLabel,
  directionTone,
  feedbackBlockedReason,
  hasGaps,
  headline,
  needsCorrection,
  needsNote,
  ownerText,
  priorityText,
  stageLabel,
  statusLabel,
  urgencyLabel,
} from "@/lib/triage-view";
import type { FeedbackVerdict, QueueItem } from "@/types/triage";

/**
 * The priority queue, the AI card and the feedback loop — sections 15, 16
 * and 20 of the requirement document.
 *
 * This is the screen a maintenance team opens in the morning: of everything
 * the platform is saying, which three things matter today. Two decisions
 * shape it.
 *
 * **An empty queue is explained, never left blank.** On this gateway it is
 * always empty, and the reason is not that the machines are healthy — a
 * 0.278 s capture cannot separate a bearing defect frequency from an
 * ordinary shaft harmonic, so no fault rule can fire. A blank panel would
 * read as a clean bill of health on a plant nobody can currently diagnose.
 *
 * **Every ranking shows what it could not see.** A priority computed from
 * half the inputs looks exactly like one computed from all of them, so the
 * gaps are listed on the card rather than folded into the number.
 */

const DIRECTION_ICON = {
  rising: ArrowUpRight,
  falling: ArrowDownRight,
  steady: Minus,
  unknown: ShieldQuestion,
} as const;

function TrendChip({ item }: { item: QueueItem }) {
  const Icon = DIRECTION_ICON[item.trend_direction] ?? ShieldQuestion;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-g1 text-xs font-medium",
        directionTone(item.trend_direction),
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {directionLabel(item.trend_direction)}
    </span>
  );
}

/**
 * Section 20's AI card. The fields are the document's, in its order, and a
 * field the platform could not fill says so in words.
 */
function AiCard({
  item,
  onFeedback,
  onAssign,
}: {
  item: QueueItem;
  onFeedback: () => void;
  onAssign: (analyst: string | null) => void;
}) {
  const [analyst, setAnalyst] = useState(item.assigned_analyst ?? "");

  return (
    <GlassCard className="p-g4">
      <div className="flex flex-wrap items-start justify-between gap-g2">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-helper">
            Rank {item.rank} &middot; channel {item.channel}
            {item.family ? ` · ${item.family}` : ""}
          </p>
          <h3 className="text-base font-semibold text-card-title truncate">
            {item.machine_name ?? "Unnamed machine"}
          </h3>
          <p className="text-sm text-foreground mt-g1">{headline(item)}</p>
        </div>

        <span
          className={cn(
            "shrink-0 rounded-full border px-g2 py-g1 text-xs font-semibold",
            BAND_CHIP[item.priority_band],
          )}
        >
          {BAND_LABEL[item.priority_band]} &middot; {priorityText(item)}
        </span>
      </div>

      {item.shutdown_advised ? (
        <p className="mt-g3 flex items-start gap-g2 rounded-md border border-machine-critical bg-machine-critical/10 p-g2 text-sm text-machine-critical">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            Stopping the machine is on the table. This is the only level at
            which the platform says that, and it is reached only when the
            capture could be trusted and the spectrum could see the fault.
          </span>
        </p>
      ) : null}

      <dl className="mt-g3 grid gap-g2 sm:grid-cols-2">
        <Field label="Fault suspected" value={item.fault_suspected} />
        <Field
          label="Severity"
          value={`${stageLabel(item.stage)} (${item.severity} of 5)`}
        />
        <Field
          label="Confidence"
          value={`${Math.round(item.confidence * 100)}%`}
        />
        <Field label="Urgency" value={urgencyLabel(item.urgency)} />
        <Field label="Time since first detected" value={ageText(item)} />
        <Field label="Status" value={statusLabel(item.status)} />
      </dl>

      <div className="mt-g2">
        <TrendChip item={item} />
      </div>

      {item.recommended_action ? (
        <div className="mt-g3 rounded-md border border-border bg-surface p-g2">
          <p className="text-xs font-semibold uppercase tracking-wide text-helper">
            Recommended action
          </p>
          <p className="mt-g1 text-sm text-foreground">
            {item.recommended_action}
          </p>
        </div>
      ) : null}

      <details className="mt-g3">
        <summary className="cursor-pointer text-sm font-medium text-brand">
          Why this rank?
        </summary>
        <p className="mt-g2 text-sm text-muted-foreground">
          {item.priority_reason}
        </p>
      </details>

      {hasGaps(item) ? (
        <details className="mt-g2">
          <summary className="cursor-pointer text-sm font-medium text-helper">
            <Info className="mr-g1 inline h-3.5 w-3.5" aria-hidden />
            {item.unknowns.length} thing(s) the platform could not see
          </summary>
          <ul className="mt-g2 space-y-g1 text-sm text-muted-foreground">
            {item.unknowns.map((gap) => (
              <li key={gap} className="flex gap-g2">
                <span aria-hidden>&middot;</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="mt-g4 flex flex-wrap items-center gap-g2 border-t border-border pt-g3">
        <label className="sr-only" htmlFor={`analyst-${item.rank}`}>
          Assign an analyst
        </label>
        <input
          id={`analyst-${item.rank}`}
          value={analyst}
          onChange={(event) => setAnalyst(event.target.value)}
          placeholder={ownerText(item)}
          className="min-w-0 flex-1 rounded-md border border-border bg-card px-g2 py-g1 text-sm text-foreground placeholder:text-helper"
        />
        <button
          type="button"
          onClick={() => onAssign(analyst.trim() || null)}
          className="btn-cta-outline inline-flex items-center gap-g1 rounded-md px-g3 py-g1 text-sm font-medium"
        >
          <UserCheck className="h-4 w-4" aria-hidden />
          Assign
        </button>
        <button
          type="button"
          onClick={onFeedback}
          className="btn-cta-outline inline-flex items-center gap-g1 rounded-md px-g3 py-g1 text-sm font-medium"
        >
          <ClipboardList className="h-4 w-4" aria-hidden />
          Was this right?
        </button>
      </div>
    </GlassCard>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-helper">{label}</dt>
      <dd className="text-sm text-foreground">{value}</dd>
    </div>
  );
}

/**
 * Section 16.1's eleven options.
 *
 * Each one shows what it actually changes, fetched from the platform rather
 * than written here. An analyst who cannot see what their answer does has
 * no reason to give one, and section 16.2 is a promise that it is used.
 */
function FeedbackPanel({
  item,
  onClose,
}: {
  item: QueueItem;
  onClose: () => void;
}) {
  const { verdicts, isLoading } = useVerdicts();
  const submit = useSubmitFeedback();

  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(null);
  const [note, setNote] = useState("");
  const [correction, setCorrection] = useState("");

  const chosen = verdicts.find((option) => option.value === verdict);
  const blocked = feedbackBlockedReason(verdict, note, correction);

  return (
    <GlassCard className="p-g4">
      <div className="flex items-start justify-between gap-g2">
        <div>
          <h3 className="text-base font-semibold text-card-title">
            What did you find on {item.machine_name ?? "this machine"}?
          </h3>
          <p className="text-sm text-muted-foreground">
            {item.fault_suspected} &middot; channel {item.channel}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-brand underline"
        >
          Close
        </button>
      </div>

      {isLoading ? (
        <p className="mt-g3 text-sm text-muted-foreground">
          Loading the options&hellip;
        </p>
      ) : (
        <div className="mt-g3 grid gap-g2 sm:grid-cols-2">
          {verdicts.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setVerdict(option.value)}
              className={cn(
                "rounded-md border p-g2 text-left transition",
                verdict === option.value
                  ? "border-brand bg-surface"
                  : "border-border bg-card hover:border-brand",
              )}
            >
              <span className="block text-sm font-medium text-foreground">
                {option.label}
              </span>
              <span className="mt-g1 block text-xs text-muted-foreground">
                {option.effect}
              </span>
            </button>
          ))}
        </div>
      )}

      {verdict && needsCorrection(verdict) ? (
        <div className="mt-g3">
          <label
            htmlFor="corrected-fault"
            className="text-xs font-semibold uppercase tracking-wide text-helper"
          >
            What was it actually?
          </label>
          <input
            id="corrected-fault"
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            placeholder="e.g. bearing_inner_race, or a name for a new fault"
            className="mt-g1 w-full rounded-md border border-border bg-card px-g2 py-g1 text-sm text-foreground placeholder:text-helper"
          />
        </div>
      ) : null}

      <div className="mt-g3">
        <label
          htmlFor="feedback-note"
          className="text-xs font-semibold uppercase tracking-wide text-helper"
        >
          Notes {verdict && needsNote(verdict) ? "(required)" : "(optional)"}
        </label>
        <textarea
          id="feedback-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
          className="mt-g1 w-full rounded-md border border-border bg-card px-g2 py-g1 text-sm text-foreground placeholder:text-helper"
          placeholder="What you saw, and where."
        />
      </div>

      {chosen ? (
        <p className="mt-g3 rounded-md border border-border bg-surface p-g2 text-sm text-muted-foreground">
          <strong className="text-foreground">What this changes: </strong>
          {chosen.effect} <br />
          <strong className="text-foreground">Why it is kept: </strong>
          {chosen.learns}
        </p>
      ) : null}

      {submit.isSuccess && submit.data ? (
        <div className="mt-g3 rounded-md border border-brand bg-surface p-g2 text-sm">
          <p className="flex items-center gap-g2 font-medium text-brand">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            Recorded.
          </p>
          <p className="mt-g1 text-muted-foreground">
            {submit.data.standing.reason}
          </p>
          {submit.data.applied.map((line) => (
            <p key={line} className="mt-g1 text-muted-foreground">
              {line}
            </p>
          ))}
        </div>
      ) : null}

      {submit.isError ? (
        <p className="mt-g3 text-sm text-machine-critical">
          That could not be recorded. Nothing has been changed.
        </p>
      ) : null}

      <div className="mt-g3 flex flex-wrap items-center gap-g2">
        <button
          type="button"
          disabled={Boolean(blocked) || submit.isPending}
          onClick={() =>
            verdict &&
            submit.mutate({
              findingId: item.finding_id,
              body: {
                verdict,
                note: note.trim() || null,
                corrected_fault_key: needsCorrection(verdict)
                  ? correction.trim()
                  : null,
              },
            })
          }
          className="btn-cta-outline rounded-md px-g3 py-g1 text-sm font-medium disabled:opacity-50"
        >
          {submit.isPending ? "Recording…" : "Submit"}
        </button>
        {blocked ? (
          <span className="text-sm text-helper">{blocked}</span>
        ) : null}
      </div>
    </GlassCard>
  );
}

export function TriagePage() {
  const [includeSuppressed, setIncludeSuppressed] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const { items, reason, isLoading, isError } = useTriageQueue(
    50,
    includeSuppressed,
  );
  const { summary } = useFeedbackSummary();
  const assign = useAssignFinding();

  const selected = useMemo(
    () => items.find((item) => item.rank === open) ?? null,
    [items, open],
  );

  return (
    <div className="space-y-g4">
      <PageHero
        title="Priority queue"
        subtitle="Of everything the platform is reporting, what to attend to first — ranked by how bad the fault is, how much the machine matters, and how well it can actually be seen."
        vibrationBg
      />

      <div className="flex flex-wrap items-center gap-g3">
        <label className="flex items-center gap-g2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={includeSuppressed}
            onChange={(event) => setIncludeSuppressed(event.target.checked)}
          />
          Show findings analysts have muted
        </label>
        {summary ? (
          <span className="text-sm text-muted-foreground">
            {summary.total} analyst report(s) &middot; {summary.confirmed}{" "}
            confirmed &middot; {summary.rejected} rejected
          </span>
        ) : null}
      </div>

      {isLoading ? (
        <GlassCard className="p-g4">
          <p className="text-sm text-muted-foreground">
            Building the queue&hellip;
          </p>
        </GlassCard>
      ) : null}

      {isError ? (
        <GlassCard className="p-g4">
          <p className="flex items-start gap-g2 text-sm text-machine-critical">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              The queue could not be loaded. That is not the same as an empty
              queue — nothing is known about what needs attention right now.
            </span>
          </p>
        </GlassCard>
      ) : null}

      {!isLoading && !isError && items.length === 0 ? (
        <GlassCard className="p-g4">
          <p className="flex items-start gap-g2 text-sm text-foreground">
            <ShieldQuestion
              className="mt-0.5 h-4 w-4 shrink-0 text-helper"
              aria-hidden
            />
            <span>{reason}</span>
          </p>
        </GlassCard>
      ) : null}

      {/*
        The feedback panel opens directly under the card it belongs to.
        Rendering it once at the end of the list put it below every other
        finding, so clicking "Was this right?" on the top row scrolled the
        analyst away from the card they were answering about.
      */}
      <div className="grid gap-g3">
        {items.map((item) => (
          <div
            key={`${item.sensor_id}-${item.channel}-${item.fault_key}`}
            className="grid gap-g2"
          >
            <AiCard
              item={item}
              onFeedback={() =>
                setOpen(open === item.rank ? null : item.rank)
              }
              onAssign={(analyst) =>
                assign.mutate({ findingId: item.finding_id, body: { analyst } })
              }
            />
            {selected && selected.rank === item.rank ? (
              <FeedbackPanel item={selected} onClose={() => setOpen(null)} />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

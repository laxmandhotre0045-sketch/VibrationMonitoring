import React, { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  Info,
  Send,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { askAI, getAIAnalysis, getAIStatus, getAISummary } from "@/api/ai";
import type { AIAnswer, AIFinding } from "@/types/dashboard";

/**
 * MOM items 4, 5, 6 and 9 — the AI surface.
 *
 * Two things this page does that a conventional "AI panel" does not, both
 * because of what the underlying data is:
 *
 * It says who wrote the prose. `source` is shown, not hidden. A reader is
 * entitled to know whether a sentence came from a language model or from the
 * platform's own template, and it is the first thing to check when the wording
 * looks odd.
 *
 * It gives refusals the same weight as answers. "This data cannot answer that"
 * is the correct response to most questions about a stopped machine, and
 * styling it as an error would train people to treat the honest answer as a
 * malfunction.
 */

const SEVERITY: Record<
  AIFinding["severity"],
  { label: string; icon: typeof Info; cls: string; ring: string }
> = {
  critical: { label: "Critical", icon: TriangleAlert, cls: "text-machine-critical", ring: "border-machine-critical/40" },
  warning: { label: "Warning", icon: AlertTriangle, cls: "text-machine-warning", ring: "border-machine-warning/40" },
  advisory: { label: "Advisory", icon: Info, cls: "text-signal-dark", ring: "border-signal-dark/30" },
  informational: { label: "Note", icon: Info, cls: "text-muted-foreground", ring: "border-border" },
};

function FindingRow({ finding }: { finding: AIFinding }) {
  const meta = SEVERITY[finding.severity] ?? SEVERITY.informational;
  const Icon = meta.icon;
  return (
    <li className="border-b border-border py-3 last:border-b-0">
      <div className="flex items-start gap-2.5">
        <Icon size={15} className={cn("mt-0.5 shrink-0", meta.cls)} />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{finding.title}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{finding.detail}</p>
          {finding.caveat && (
            /* Not a footnote. The caveat is what stops a true statement being
               used for a question it does not answer, so it is shown with the
               claim rather than tucked behind a toggle. */
            <p className="mt-1.5 border-l-2 border-machine-warning/50 pl-2 text-xs text-muted-foreground">
              {finding.caveat}
            </p>
          )}
          <p className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">
            {meta.label} · confidence {finding.confidence}
            {finding.channel_index !== null && ` · ch${finding.channel_index}`}
          </p>
        </div>
      </div>
    </li>
  );
}

function AnswerBlock({ answer }: { answer: AIAnswer }) {
  const refused = answer.source !== "model";
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        refused ? "border-border bg-muted/40" : "border-signal-dark/25 bg-white",
      )}
    >
      <p className="mb-1.5 text-xs text-muted-foreground">{answer.question}</p>
      <p className="text-sm text-foreground">{answer.answer}</p>
      {answer.refused_reason && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
          <Ban size={12} className="mt-0.5 shrink-0" />
          {answer.refused_reason}
        </p>
      )}
      {answer.source === "model" && answer.model && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Written by {answer.model} from the findings above. Every number in it
          was checked against them.
        </p>
      )}
    </div>
  );
}

export function AIAnalysisPage() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<AIAnswer[]>([]);

  const status = useQuery({ queryKey: ["ai-status"], queryFn: getAIStatus, retry: 1 });
  const summary = useQuery({
    queryKey: ["ai-summary"],
    queryFn: () => getAISummary(),
    retry: 1,
    refetchInterval: 120_000,
  });
  const analysis = useQuery({
    queryKey: ["ai-analysis"],
    queryFn: () => getAIAnalysis(),
    retry: 1,
    refetchInterval: 120_000,
  });

  const askMutation = useMutation({
    mutationFn: (q: string) => askAI(q),
    onSuccess: (a) => setAsked((prev) => [a, ...prev].slice(0, 8)),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || askMutation.isPending) return;
    askMutation.mutate(q);
    setQuestion("");
  }

  const findings = analysis.data?.findings ?? [];
  const cannot = analysis.data?.cannot_conclude ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="rounded-lg border border-border bg-white p-2">
          <Sparkles className="h-5 w-5 text-signal-dark" />
        </div>
        <div>
          <h1 className="text-xl font-semibold">AI Analysis</h1>
          <p className="text-sm text-muted-foreground">
            What the measurements support, in plain language — and what they do
            not.
          </p>
        </div>
      </div>

      <GlassCard className="p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold">Summary</h2>
          {summary.data && (
            <span className="text-xs text-muted-foreground">
              {summary.data.source === "model"
                ? `written by ${summary.data.model}`
                : "written by the platform"}
            </span>
          )}
        </div>

        {summary.isLoading && (
          <p className="mt-3 text-sm text-muted-foreground">Reading the measurements…</p>
        )}
        {summary.data && (
          <>
            <p className="mt-2 text-sm font-medium text-foreground">
              {summary.data.headline}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">{summary.data.summary}</p>

            {summary.data.rejected_reason && (
              /* Surfaced deliberately. A pattern of rejections means the model
                 is drifting, and hiding it would make that invisible. */
              <p className="mt-2 flex items-start gap-1.5 rounded border border-machine-warning/30 bg-machine-warning/5 p-2 text-xs text-muted-foreground">
                <Ban size={12} className="mt-0.5 shrink-0" />
                A generated summary was withheld: {summary.data.rejected_reason}.
                The text above is the platform's own.
              </p>
            )}

            {summary.data.suggestions.length > 0 && (
              <ul className="mt-3 space-y-1 border-t border-border pt-3">
                {summary.data.suggestions.map((s) => (
                  <li key={s} className="flex gap-2 text-sm text-foreground">
                    <span className="text-signal-dark">→</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard className="p-4">
          <h2 className="text-sm font-semibold">Findings</h2>
          {analysis.isLoading && (
            <p className="mt-3 text-sm text-muted-foreground">Analysing…</p>
          )}
          {!analysis.isLoading && findings.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No findings. Either nothing has been measured yet, or nothing is
              worth reporting.
            </p>
          )}
          <ul className="mt-1">
            {findings.map((f, i) => (
              <FindingRow key={`${f.code}-${f.channel_index}-${i}`} finding={f} />
            ))}
          </ul>
        </GlassCard>

        <div className="space-y-4">
          {cannot.length > 0 && (
            <GlassCard className="p-4">
              <h2 className="text-sm font-semibold">What this data cannot answer</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Stated so that a question landing here gets a reason rather than
                a guess.
              </p>
              <ul className="mt-2 space-y-1.5">
                {cannot.map((c) => (
                  <li key={c} className="flex gap-2 text-sm text-muted-foreground">
                    <Ban size={13} className="mt-0.5 shrink-0" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </GlassCard>
          )}

          <GlassCard className="p-4">
            <h2 className="text-sm font-semibold">Ask about this machine</h2>
            {status.data && !status.data.llm_configured && (
              <p className="mt-2 rounded border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
                No language model is configured, so questions cannot be answered
                in prose. The findings are still shown.
              </p>
            )}
            <form onSubmit={submit} className="mt-2 flex gap-2">
              <input
                id="ai-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                maxLength={500}
                placeholder="Is the pump healthy?"
                className="min-w-0 flex-1 rounded-md border border-border bg-white px-3 py-2 text-sm"
              />
              <Button
                type="submit"
                disabled={!question.trim() || askMutation.isPending}
                icon={<Send size={15} />}
              >
                {askMutation.isPending ? "Asking…" : "Ask"}
              </Button>
            </form>

            {askMutation.isError && (
              <p className="mt-2 text-xs text-machine-critical">
                The question could not be sent. Check the connection and retry.
              </p>
            )}

            <div className="mt-3 space-y-2">
              {asked.map((a) => (
                <AnswerBlock key={a.generated_at + a.question} answer={a} />
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

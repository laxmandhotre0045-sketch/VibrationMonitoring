import React, { useState } from "react";
import { Check, Copy, Loader2, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export const platformTableWrapper =
  "overflow-x-auto rounded-lg border border-border bg-white";
export const platformTable = "w-full min-w-[640px] text-sm";
export const platformTh =
  "px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-muted-foreground bg-warm border-b border-border whitespace-nowrap";
export const platformTd = "px-4 py-3 align-middle border-b border-border/70";

interface StatusPillProps {
  tone: "healthy" | "muted" | "warning" | "danger";
  children: React.ReactNode;
}

const PILL_TONES: Record<StatusPillProps["tone"], string> = {
  healthy: "bg-machine-healthy/10 text-machine-healthy border-machine-healthy/25",
  muted: "bg-muted text-muted-foreground border-border",
  warning: "bg-[#FFA500]/12 text-signal-dark border-[#FFA500]/30",
  danger: "bg-destructive/10 text-destructive border-destructive/25",
};

export function StatusPill({ tone, children }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap",
        PILL_TONES[tone]
      )}
    >
      {children}
    </span>
  );
}

export function EmptyRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-g4 py-g6 text-center text-sm text-muted-foreground">
        {message}
      </td>
    </tr>
  );
}

export function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-g4 py-g6 text-center text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          Loading…
        </span>
      </td>
    </tr>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      {message}
    </div>
  );
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface SecretRevealProps {
  label: string;
  secret: string;
  /** What the operator loses if they navigate away without copying. */
  warning: string;
}

/**
 * The one-time display of an API key or signing secret. The value is not
 * recoverable from the server afterwards, so the copy affordance and the
 * warning are load-bearing rather than decorative.
 */
export function SecretReveal({ label, secret, warning }: SecretRevealProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the value stays selectable in the
      // field either way, so there is nothing to recover from here.
      setCopied(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3 rounded-lg border border-[#FFA500]/35 bg-[#FFA500]/8 px-4 py-3">
        <ShieldAlert size={18} className="mt-0.5 shrink-0 text-signal-dark" />
        <p className="text-sm text-foreground leading-relaxed">{warning}</p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <div className="flex items-stretch gap-2">
          <input
            readOnly
            value={secret}
            onFocus={(event) => event.currentTarget.select()}
            className="flex-1 min-w-0 rounded-lg border border-border bg-warm px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]"
          />
          <button
            type="button"
            onClick={copy}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-2.5 text-sm font-semibold text-brand hover:border-signal-light/60 hover:bg-warm"
          >
            {copied ? <Check size={15} className="text-machine-healthy" /> : <Copy size={15} />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface IconActionProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  tone?: "default" | "danger";
}

export function IconAction({ label, tone = "default", className, ...props }: IconActionProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={cn(
        "rounded-lg border border-transparent p-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
        tone === "danger"
          ? "text-muted-foreground hover:border-destructive/25 hover:bg-destructive/8 hover:text-destructive"
          : "text-muted-foreground hover:border-border hover:bg-warm hover:text-brand",
        className
      )}
      {...props}
    />
  );
}

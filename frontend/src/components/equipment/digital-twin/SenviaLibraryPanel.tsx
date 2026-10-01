import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Box, Info } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
import { useTheme } from "@/contexts/ThemeContext";
import { libraryIdForMachineType, libraryModel } from "@/lib/senvia-3d/library-models";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

/**
 * The Senvia 3D equipment library, embedded in the equipment form.
 *
 * The library is the kit's own page, served from `public/senvia-3d/library.html`
 * and built from `senvia-3d/legacy/senvia_3d_library.html` by
 * `tools/build_web_library.py`. It is not reimplemented here, and that is the
 * point: it draws 48 machines with the rotation physics, ISO point numbering,
 * RAL paint and the full toolbar — sample condition, rotate shafts, see inside,
 * flow, sensors, rotation direction, arrows, guards, save image, export GLB —
 * already reviewed and already passing the kit's own bug hunt. Rebuilding any
 * of that in React would mean re-deriving physics we have a working, checked
 * copy of.
 *
 * It runs in an iframe for one substantial reason: the library is built against
 * three.js **r128**, and Senvia's own bundle is on 0.169. three changed its
 * default colour management in r152, so running the library's geometry through
 * the app's three would shift every RAL paint colour away from the rendering
 * the machines were signed off at. The frame gives the library its own r128 and
 * its own WebGL context, and keeps the two versions from ever meeting.
 *
 * Talking to it goes through `postMessage`, confined to this origin — the frame
 * is served by Senvia itself. Only model ids and point numbers cross; no
 * customer data goes in and none comes out.
 */

interface SenviaLibraryPanelProps {
  /** Drives the caption only — one viewer serves every step of the form. */
  activeStep: number;
  /**
   * Accepted so this drops into `DigitalTwinSection` beside the other panels.
   * The library draws a machine *type*, not one customer's asset; binding a
   * saved equipment row to its measurement points is the next piece of work
   * (`pointClick` already reports which point was tapped).
   */
  equipmentId?: string;
  className?: string;
}

/** Messages the embedded library sends back. */
interface BridgeMessage {
  source?: string;
  type?: string;
  id?: string;
  name?: string;
  drive?: string;
  points?: number;
  number?: number;
  label?: string;
  message?: string;
}

const STEP_CAPTION: Record<number, string> = {
  1: "Pick a Machine Type in Step 1 and the library opens on that machine.",
  2: "Mechanical details describe the machine shown here.",
  3: "See inside to check the bearings and the shaft line.",
  4: "Operating conditions apply to the machine shown here.",
  5: "Tap a numbered point to read which measurement it carries.",
  6: "Check the machine and its measurement points before you save.",
};

/** A compact count, so the header says what is on screen at a glance. */
function HeaderStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-end leading-none">
      <span className="text-sm font-bold tabular-nums text-foreground">{value}</span>
      <span className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

export function SenviaLibraryPanel({ activeStep, className }: SenviaLibraryPanelProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [shown, setShown] = useState<{ id: string; name: string; points: number } | null>(null);
  const [lastPoint, setLastPoint] = useState<{ number: number; label: string } | null>(null);

  const form = useFormContext<EquipmentFormData>();
  const machineType = form?.watch("machine_type") as string | undefined;
  const wantedId = useMemo(() => libraryIdForMachineType(machineType), [machineType]);
  const { theme } = useTheme();

  /**
   * The frame's src is fixed for the life of the panel.
   *
   * Changing it would reload the page and throw away the WebGL context every
   * time somebody edits Machine Type in Step 1. The initial model rides on the
   * query string so the first paint is already the right machine; every later
   * change is a message.
   */
  const initialSrc = useMemo(() => {
    const base = "/senvia-3d/library.html";
    const first = libraryIdForMachineType(form?.getValues?.("machine_type") as string | undefined);
    return first ? `${base}?model=${encodeURIComponent(first)}` : base;
    // Deliberately computed once: see above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const send = useCallback((message: Record<string, unknown>) => {
    const frame = frameRef.current;
    if (!frame?.contentWindow) return;
    frame.contentWindow.postMessage({ target: "senvia-3d", ...message }, window.location.origin);
  }, []);

  // Hear back from the library.
  useEffect(() => {
    function onMessage(event: MessageEvent<BridgeMessage>) {
      // Same-origin only. The frame is our own asset; anything else talking on
      // this channel is not something to act on.
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (!data || data.source !== "senvia-3d") return;

      if (data.type === "ready") setReady(true);
      else if (data.type === "shown" && data.id) {
        setShown({ id: data.id, name: data.name ?? data.id, points: data.points ?? 0 });
        setLastPoint(null);
      } else if (data.type === "pointClick" && typeof data.number === "number") {
        setLastPoint({ number: data.number, label: data.label ?? "" });
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  // Follow Machine Type once the library is up.
  useEffect(() => {
    if (!ready || !wantedId) return;
    if (shown?.id === wantedId) return;
    send({ type: "show", id: wantedId });
  }, [ready, wantedId, shown?.id, send]);

  /**
   * Follow Senvia's theme rather than the operating system's.
   *
   * The library's own stylesheet answers to `data-theme`, but a frame has no
   * idea which theme the app around it is wearing — so a dark Senvia would
   * otherwise frame a white panel on any machine whose OS is set to light.
   */
  useEffect(() => {
    if (!ready) return;
    send({ type: "theme", theme });
  }, [ready, theme, send]);

  const mapped = libraryModel(wantedId);
  const caption = STEP_CAPTION[activeStep] ?? STEP_CAPTION[1];

  return (
    <section className={cn("content-card", cardHover.soft, className)} aria-label="3D equipment library">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <Box className="h-5 w-5 text-primary" aria-hidden="true" />
          <div>
            <h3 className="text-base font-semibold leading-tight text-foreground">
              3D equipment library
            </h3>
            <p className="text-xs text-muted-foreground">{caption}</p>
          </div>
        </div>
        <div className="flex items-center gap-5">
          <HeaderStat value={shown ? String(shown.points) : "—"} label="points" />
          <HeaderStat value={shown?.name ?? (mapped?.name ?? "—")} label="machine" />
        </div>
      </div>

      {/* The library is a full page in its own right — stage, chips, toolbar —
          so it needs real height. Below the fold on a phone it still scrolls
          its own panel rather than the form. */}
      <div className="relative mt-3 overflow-hidden rounded-lg border border-border/60 bg-background">
        {!ready && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
            <p className="text-sm text-muted-foreground">Loading the 3D library…</p>
          </div>
        )}
        <iframe
          ref={frameRef}
          src={initialSrc}
          title="Senvia 3D equipment library"
          className="block h-[78vh] min-h-[560px] w-full border-0"
          // Same-origin so the bridge can talk; downloads so "Save image" and
          // "Export 3D (GLB)" reach the browser's download path.
          sandbox="allow-scripts allow-same-origin allow-downloads"
          loading="lazy"
        />
      </div>

      <div className="mt-3 flex flex-wrap items-start gap-2 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <p className="min-w-0">
          {lastPoint ? (
            <>
              Point {lastPoint.number}: <span className="text-foreground">{lastPoint.label}</span>
            </>
          ) : machineType && !wantedId ? (
            <>
              No library machine is a direct match for{" "}
              <span className="text-foreground">{machineType}</span> — pick the closest one from
              the chips below the view.
            </>
          ) : (
            <>
              Drag to rotate, scroll to zoom. Every machine in the library is reachable from the
              chips; the toolbar turns the shafts, opens the casing and shows the flow.
            </>
          )}
        </p>
      </div>
    </section>
  );
}

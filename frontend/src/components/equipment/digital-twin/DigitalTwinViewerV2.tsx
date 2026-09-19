import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Box, Eye, Loader2, RotateCw, Tag } from "lucide-react";
import type {
  MachineTypeId,
  TwinBearing,
  TwinSensor,
} from "@/lib/digital-twin/types";
import { previewUrlFor } from "@/lib/digital-twin/machine-type-map";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/lib/utils";
import {
  CameraRig,
  framingFor,
  type CameraViewId,
} from "./scene/camera-rig";
import { createStage, fitShadowFloor, CAMERA_FOV, type Stage } from "./scene/renderer";
import { disposeObject } from "./scene/dispose";
import { loadModelSource, type LoadedModel } from "./scene/model-source";
import {
  createBearingMarker,
  createSensorMarker,
  markerColor,
  UNMAPPED_COLOR,
} from "./scene/markers";
import { XrayController } from "./scene/xray";
import {
  LabelOverlay,
  type AnchorProjection,
  type LabelOverlayHandle,
  type OverlayItem,
} from "./overlay/LabelOverlay";

export interface DigitalTwinViewerProps {
  machineType: MachineTypeId;
  bearings: TwinBearing[];
  sensors: TwinSensor[];
  /** Owned by the parent so the side panel and the 3D view stay in lockstep. */
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onSelect: (id: string) => void;
  className?: string;
}

/** Drag further than this and the pointer-up is a drag, not a click. */
const CLICK_SLOP = 5;
/** Occlusion raycasts are the expensive part of a frame; throttle hard. */
const OCCLUSION_INTERVAL_MS = 140;
const HOVER_INTERVAL_MS = 60;
const SHAFT_RPM = 24;

interface MarkerEntry {
  object: THREE.Object3D;
  /** Point the leader line ends on — the top of the sensor, ring of a bearing. */
  labelAnchor: THREE.Object3D;
  setHighlighted: (on: boolean) => void;
}

const VIEW_BUTTONS: { id: CameraViewId; label: string }[] = [
  { id: "iso", label: "Reset view" },
  { id: "front", label: "Front" },
  { id: "side", label: "Side" },
  { id: "top", label: "Top" },
];

/**
 * The 3D Digital Twin.
 *
 * Renders a real model per machine type under studio lighting, with boundary
 * HTML labels, x-ray, and two-way highlighting against the side panel.
 *
 * ## Render loop
 * The loop is **gated**, not continuous. It runs while something is actually
 * moving — a camera tween, damping settling, the x-ray fade, the shaft
 * turning, a pointer down — and stops otherwise, after one final frame. An
 * industrial console left open on this page all day therefore costs nothing
 * once the operator stops touching it, while damping and the 650 ms view moves
 * still get the per-frame updates they need. It also stops entirely when the
 * component scrolls off-screen or the tab is hidden.
 *
 * ## three vs React
 * three owns the scene graph in refs; React owns the DOM and the props. Labels
 * are HTML, but they are *positioned* imperatively through the overlay handle
 * — re-rendering a dozen components every frame to move them a few pixels is
 * what makes a viewer feel slow.
 */
export function DigitalTwinViewer({
  machineType,
  bearings,
  sensors,
  highlightedId,
  onHighlight,
  onSelect,
  className,
}: DigitalTwinViewerProps) {
  const { theme } = useTheme();

  const stageRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<LabelOverlayHandle | null>(null);

  const three = useRef<Stage | null>(null);
  const rigRef = useRef<CameraRig | null>(null);
  const modelRef = useRef<LoadedModel | null>(null);
  const xrayRef = useRef<XrayController | null>(null);
  const markersRef = useRef(new Map<string, MarkerEntry>());
  const boxRef = useRef(new THREE.Box3());

  const frameRef = useRef<number | null>(null);
  const clockRef = useRef(new THREE.Clock());
  const pausedRef = useRef(false);
  const occlusionRef = useRef({ last: 0, blocked: new Set<string>() });

  // Props the loop reads. Held in refs so changing them never re-creates it.
  const highlightRef = useRef(highlightedId);
  const onHighlightRef = useRef(onHighlight);
  const onSelectRef = useRef(onSelect);
  highlightRef.current = highlightedId;
  onHighlightRef.current = onHighlight;
  onSelectRef.current = onSelect;

  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [view, setView] = useState<CameraViewId>("iso");
  const [xrayOn, setXrayOn] = useState(false);
  const [runShaft, setRunShaft] = useState(false);
  const [labelsOn, setLabelsOn] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);

  const xrayOnRef = useRef(xrayOn);
  const runShaftRef = useRef(runShaft);
  const labelsOnRef = useRef(labelsOn);
  xrayOnRef.current = xrayOn;
  runShaftRef.current = runShaft && !reducedMotion;
  labelsOnRef.current = labelsOn;

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  // --- Label chips -------------------------------------------------------
  const overlayItems = useMemo<OverlayItem[]>(
    () => [
      ...sensors.map((sensor) => ({
        id: sensor.id,
        primary: sensor.id,
        secondary: sensor.axis,
        row: "sensor" as const,
        status: sensor.status,
      })),
      ...bearings.map((bearing) => ({
        id: bearing.id,
        primary: bearing.name,
        secondary: bearing.configured ? bearing.note ?? "Configured" : "Not configured",
        row: "bearing" as const,
        muted: !bearing.configured,
      })),
    ],
    [sensors, bearings]
  );

  // ---------------------------------------------------------------------
  // Render loop
  // ---------------------------------------------------------------------

  /** Returns true when another frame is needed to finish placing chips. */
  const projectLabels = useCallback((): boolean => {
    const stage = three.current;
    const host = stageRef.current;
    const overlay = overlayRef.current;
    if (!stage || !host || !overlay || !labelsOnRef.current) return false;

    const width = host.clientWidth;
    const height = host.clientHeight;
    if (width === 0 || height === 0) return true;

    const positions = new Map<string, AnchorProjection>();
    const point = new THREE.Vector3();

    markersRef.current.forEach((entry, id) => {
      entry.labelAnchor.getWorldPosition(point);
      point.project(stage.camera);
      const x = (point.x * 0.5 + 0.5) * width;
      const y = (-point.y * 0.5 + 0.5) * height;
      positions.set(id, {
        x,
        y,
        // `z >= 1` means behind the camera; a generous margin keeps a chip
        // alive just off-stage rather than popping as it crosses the edge.
        visible: point.z < 1 && x > -80 && x < width + 80 && y > -80 && y < height + 80,
        occluded: occlusionRef.current.blocked.has(id),
      });
    });

    return overlay.update({ positions, stageWidth: width, stageHeight: height });
  }, []);

  const updateOcclusion = useCallback(() => {
    const stage = three.current;
    const model = modelRef.current;
    if (!stage || !model) return;

    const now = performance.now();
    if (now - occlusionRef.current.last < OCCLUSION_INTERVAL_MS) return;
    occlusionRef.current.last = now;

    // With x-ray on the shells are see-through, so they must not count as
    // blockers — otherwise every leader would go dashed exactly when the
    // operator has made the anchors visible.
    const ignore = xrayOnRef.current ? new Set(model.xrayMeshes) : new Set<THREE.Mesh>();
    const blocked = new Set<string>();
    const raycaster = new THREE.Raycaster();
    const origin = stage.camera.position;
    const point = new THREE.Vector3();

    markersRef.current.forEach((entry, id) => {
      entry.labelAnchor.getWorldPosition(point);
      const direction = point.clone().sub(origin);
      const distance = direction.length();
      if (distance < 1e-4) return;
      raycaster.set(origin, direction.normalize());
      raycaster.far = distance - 0.12;

      const hits = raycaster.intersectObject(model.root, true);
      if (hits.some((hit) => !ignore.has(hit.object as THREE.Mesh))) blocked.add(id);
    });

    occlusionRef.current.blocked = blocked;
  }, []);

  const tick = useCallback(() => {
    frameRef.current = null;
    const stage = three.current;
    const rig = rigRef.current;
    if (!stage || !rig || pausedRef.current) return;

    const delta = Math.min(clockRef.current.getDelta(), 0.1);
    let active = rig.update(delta);
    if (xrayRef.current?.update(delta)) active = true;

    const rotor = modelRef.current?.rotor;
    if (rotor && runShaftRef.current) {
      rotor.rotation.x += delta * ((SHAFT_RPM * Math.PI * 2) / 60);
      active = true;
    }

    stage.renderer.render(stage.scene, stage.camera);
    updateOcclusion();
    // Chips mounted this frame may not have measured yet; keep the loop alive
    // one more frame rather than stopping with them hidden.
    if (projectLabels()) active = true;

    // Nothing moving? Stop the loop entirely rather than idling at 60fps.
    if (active) frameRef.current = requestAnimationFrame(tick);
  }, [projectLabels, updateOcclusion]);

  /**
   * Wake the loop. Cheap and idempotent — safe to call from any handler.
   *
   * `frameRef` is the single source of truth for "a frame is already pending",
   * and `tick` clears it before doing any work, so even a throw inside the loop
   * cannot leave the viewer permanently unable to render again.
   */
  const requestFrame = useCallback(() => {
    if (pausedRef.current || frameRef.current !== null) return;
    clockRef.current.getDelta();
    frameRef.current = requestAnimationFrame(tick);
  }, [tick]);

  // ---------------------------------------------------------------------
  // Stage lifecycle — created once
  // ---------------------------------------------------------------------
  useEffect(() => {
    const host = stageRef.current;
    if (!host) return;

    let stage: Stage;
    try {
      stage = createStage();
    } catch {
      setStatus("failed");
      setMessage(
        "This browser could not start WebGL, so the 3D view is unavailable. The configuration below is unaffected."
      );
      return;
    }
    three.current = stage;

    const canvas = stage.renderer.domElement;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.setAttribute(
      "aria-label",
      "Interactive 3D digital twin. Drag to rotate, scroll to zoom."
    );
    host.appendChild(canvas);
    canvasRef.current = canvas;

    const rig = new CameraRig(stage.camera, canvas, requestFrame);
    rigRef.current = rig;

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width === 0 || height === 0) return;
      stage.renderer.setSize(width, height, false);
      stage.camera.aspect = width / height;
      stage.camera.updateProjectionMatrix();
      overlayRef.current?.invalidateSizes();
      requestFrame();
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);

    // Pause when off-screen or the tab is hidden. An operator scrolled past
    // this panel should not be paying for it.
    const setPaused = (paused: boolean) => {
      pausedRef.current = paused;
      if (!paused) requestFrame();
    };
    const intersection = new IntersectionObserver(
      ([entry]) => setPaused(!entry.isIntersecting),
      { threshold: 0 }
    );
    intersection.observe(host);
    const onVisibility = () => setPaused(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);

    const onContextLost = (event: Event) => {
      event.preventDefault();
      setStatus("failed");
      setMessage("The 3D view lost its graphics context. Reload the page to restore it.");
    };
    canvas.addEventListener("webglcontextlost", onContextLost);

    // Web fonts land after first paint and change every chip's width.
    document.fonts?.ready.then(() => {
      overlayRef.current?.invalidateSizes();
      requestFrame();
    });

    return () => {
      canvas.removeEventListener("webglcontextlost", onContextLost);
      document.removeEventListener("visibilitychange", onVisibility);
      intersection.disconnect();
      resizeObserver.disconnect();
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;

      rig.dispose();
      rigRef.current = null;

      xrayRef.current?.dispose();
      xrayRef.current = null;
      markersRef.current.forEach((entry) => disposeObject(entry.object));
      markersRef.current.clear();
      disposeObject(modelRef.current?.root);
      modelRef.current = null;

      disposeObject(stage.content);
      stage.dispose();
      // The canvas goes with the context that was just force-lost; the next
      // mount builds a fresh one.
      canvas.remove();
      canvasRef.current = null;
      three.current = null;
    };
  }, [requestFrame]);

  // ---------------------------------------------------------------------
  // Model: loaded on machine type change
  // ---------------------------------------------------------------------
  useEffect(() => {
    const stage = three.current;
    if (!stage || status === "failed") return;

    const controller = new AbortController();
    setStatus("loading");
    setMessage(null);

    loadModelSource(machineType, controller.signal)
      .then((model) => {
        if (controller.signal.aborted) return;
        const current = three.current;
        if (!current) return;

        // Tear the old one down before the new one goes in, so two models are
        // never resident at once.
        xrayRef.current?.dispose();
        xrayRef.current = null;
        markersRef.current.forEach((entry) => disposeObject(entry.object));
        markersRef.current.clear();
        disposeObject(modelRef.current?.root);

        modelRef.current = model;
        current.content.add(model.root);

        const box = new THREE.Box3().setFromObject(model.root);
        boxRef.current = box;
        fitShadowFloor(current, box);

        xrayRef.current = new XrayController(model.xrayMeshes);
        xrayRef.current.setEnabled(xrayOnRef.current);
        // Snap rather than tween: re-applying an existing toggle to a freshly
        // loaded model should not play a fade the operator did not ask for.
        xrayRef.current.snap();

        const host = stageRef.current;
        const aspect = host && host.clientHeight > 0 ? host.clientWidth / host.clientHeight : 1.6;
        rigRef.current?.snapTo(framingFor("iso", box, aspect, CAMERA_FOV));
        setView("iso");

        setStatus("ready");
        if (model.loadError) setMessage(model.loadError);
        requestFrame();
      })
      .catch((error: unknown) => {
        if ((error as DOMException)?.name === "AbortError") return;
        setStatus("failed");
        setMessage(
          error instanceof Error ? error.message : "The 3D model could not be loaded."
        );
      });

    return () => controller.abort();
    // `status` is deliberately not a dependency: including it would reload the
    // model every time loading finished.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machineType, requestFrame]);

  // ---------------------------------------------------------------------
  // Markers: rebuilt when the configuration changes
  // ---------------------------------------------------------------------
  useEffect(() => {
    const model = modelRef.current;
    if (!model || status !== "ready") return;

    markersRef.current.forEach((entry) => disposeObject(entry.object));
    markersRef.current.clear();

    // Two sensors on the same mounting point and axis share one anchor node.
    // Nudge the second along the anchor's local X so neither becomes
    // unclickable behind the other.
    const stackCounts = new Map<string, number>();

    sensors.forEach((sensor) => {
      const anchor = model.sensorAnchors.get(sensor.anchorNode.toUpperCase());
      if (!anchor) return;

      const stack = stackCounts.get(sensor.anchorNode) ?? 0;
      stackCounts.set(sensor.anchorNode, stack + 1);

      const marker = createSensorMarker(markerColor(sensor.status));
      marker.group.position.x = stack * 0.3;
      anchor.add(marker.group);

      // The leader ends at the top of the instrument, not at its foot.
      const labelAnchor = new THREE.Object3D();
      labelAnchor.position.set(stack * 0.3, 0.3, 0);
      anchor.add(labelAnchor);

      markersRef.current.set(sensor.id, {
        object: marker.group,
        labelAnchor,
        setHighlighted: marker.setHighlighted,
      });
      marker.group.userData.pickId = sensor.id;
      marker.group.traverse((child) => {
        child.userData.pickId = sensor.id;
      });
    });

    bearings.forEach((bearing) => {
      const anchor = model.bearingAnchors.get(bearing.anchorNode.toUpperCase());
      if (!anchor) return;

      const radius = (anchor.userData.radius as number | undefined) ?? 0.45;
      const marker = createBearingMarker(radius, bearing.configured);
      anchor.add(marker.group);

      const labelAnchor = new THREE.Object3D();
      labelAnchor.position.set(0, -radius - 0.1, 0);
      anchor.add(labelAnchor);

      markersRef.current.set(bearing.id, {
        object: marker.group,
        labelAnchor,
        setHighlighted: marker.setHighlighted,
      });
      marker.group.traverse((child) => {
        child.userData.pickId = bearing.id;
      });
    });

    overlayRef.current?.invalidateSizes();
    requestFrame();
  }, [sensors, bearings, status, requestFrame]);

  // --- Highlight ---------------------------------------------------------
  useEffect(() => {
    markersRef.current.forEach((entry, id) => {
      entry.setHighlighted(id === highlightedId);
    });
    requestFrame();
  }, [highlightedId, sensors, bearings, requestFrame]);

  // --- X-ray / labels ----------------------------------------------------
  useEffect(() => {
    xrayRef.current?.setEnabled(xrayOn);
    // Blockers changed, so the dashed-leader state is stale.
    occlusionRef.current.last = 0;
    requestFrame();
  }, [xrayOn, requestFrame]);

  useEffect(() => {
    requestFrame();
  }, [runShaft, labelsOn, requestFrame]);

  // --- Named views -------------------------------------------------------
  const selectView = useCallback((next: CameraViewId) => {
    setView(next);
    const host = stageRef.current;
    const rig = rigRef.current;
    if (!host || !rig || host.clientHeight === 0) return;
    rig.flyTo(framingFor(next, boxRef.current, host.clientWidth / host.clientHeight, CAMERA_FOV));
    requestFrame();
  }, [requestFrame]);

  /** Frame the camera on one marker and select it. */
  const flyToMarker = useCallback(
    (id: string) => {
      const entry = markersRef.current.get(id);
      const rig = rigRef.current;
      const host = stageRef.current;
      if (!entry || !rig || !host || host.clientHeight === 0) return;

      const target = entry.labelAnchor.getWorldPosition(new THREE.Vector3());
      const box = new THREE.Box3().setFromCenterAndSize(
        target,
        new THREE.Vector3(2.6, 2.6, 2.6)
      );
      rig.flyTo(framingFor("iso", box, host.clientWidth / host.clientHeight, CAMERA_FOV));
      requestFrame();
    },
    [requestFrame]
  );

  const handleSelect = useCallback(
    (id: string) => {
      flyToMarker(id);
      onSelectRef.current(id);
    },
    [flyToMarker]
  );

  // --- Pointer picking on the canvas -------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || status === "failed") return;

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downAt: { x: number; y: number } | null = null;
    let lastHover = 0;

    const pick = (event: PointerEvent): string | null => {
      const stage = three.current;
      if (!stage) return null;
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, stage.camera);
      raycaster.far = Infinity;

      const targets = [...markersRef.current.values()].map((entry) => entry.object);
      const hit = raycaster.intersectObjects(targets, true)[0];
      return (hit?.object.userData.pickId as string | undefined) ?? null;
    };

    const onPointerDown = (event: PointerEvent) => {
      downAt = { x: event.clientX, y: event.clientY };
    };

    const onPointerMove = (event: PointerEvent) => {
      if (downAt) return; // orbiting, not hovering
      const now = performance.now();
      if (now - lastHover < HOVER_INTERVAL_MS) return;
      lastHover = now;
      const id = pick(event);
      if (id !== highlightRef.current) onHighlightRef.current(id);
    };

    const onPointerUp = (event: PointerEvent) => {
      const start = downAt;
      downAt = null;
      if (!start) return;
      // An orbit drag must not also count as a click on whatever it passed over.
      if (
        Math.abs(event.clientX - start.x) > CLICK_SLOP ||
        Math.abs(event.clientY - start.y) > CLICK_SLOP
      ) {
        return;
      }
      const id = pick(event);
      if (id) handleSelect(id);
    };

    const onPointerLeave = () => {
      if (highlightRef.current) onHighlightRef.current(null);
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    return () => {
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
    };
  }, [handleSelect, status]);

  const dark = theme === "dark";
  const stageStyle = {
    // The backdrop is CSS, not a scene background: the canvas is transparent,
    // so the radial gradient follows the app theme with no renderer changes.
    background: dark
      ? "radial-gradient(120% 120% at 50% 22%, #2b3442 0%, #171c24 62%, #10141a 100%)"
      : "radial-gradient(120% 120% at 50% 22%, #ffffff 0%, #f2f5fa 58%, #e6ebf3 100%)",
    "--twin-chip-bg": dark ? "rgba(30,36,43,0.92)" : "rgba(255,255,255,0.94)",
    "--twin-chip-fg": dark ? "#e8edf2" : "#1d2b3a",
    "--twin-chip-muted-fg": dark ? "#9aa7b4" : "#5c6b7a",
    "--twin-chip-muted-border": dark ? "#39424c" : "#c9d2db",
  } as React.CSSProperties;

  const toggles = [
    { id: "xray", label: "X-ray casing", on: xrayOn, set: setXrayOn, icon: <Eye size={12} /> },
    {
      id: "shaft",
      label: "Run shaft",
      on: runShaft,
      set: setRunShaft,
      icon: <RotateCw size={12} />,
      disabled: reducedMotion,
      title: reducedMotion
        ? "Disabled because this device is set to reduce motion."
        : undefined,
    },
    { id: "labels", label: "Labels", on: labelsOn, set: setLabelsOn, icon: <Tag size={12} /> },
  ];

  return (
    <div className={cn("flex flex-col gap-g3", className)}>
      <div className="flex flex-wrap items-center gap-1.5">
        {VIEW_BUTTONS.map((button) => (
          <button
            key={button.id}
            type="button"
            onClick={() => selectView(button.id)}
            disabled={status !== "ready"}
            className={cn(
              "min-h-[32px] rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60",
              "disabled:opacity-50",
              view === button.id
                ? "border-[#FF6B00] bg-[#FF6B00]/10 text-[#FF6B00]"
                : "border-border bg-white text-muted-foreground hover:border-[#FF6B00]/40 hover:text-foreground"
            )}
          >
            {button.label}
          </button>
        ))}

        <span className="mx-1 h-5 w-px bg-border" aria-hidden />

        {toggles.map((toggle) => (
          <button
            key={toggle.id}
            type="button"
            aria-pressed={toggle.on}
            disabled={status !== "ready" || toggle.disabled}
            title={toggle.title}
            onClick={() => toggle.set(!toggle.on)}
            className={cn(
              "inline-flex min-h-[32px] items-center gap-1.5 rounded-md border px-2.5 py-1.5",
              "text-xs font-semibold transition-colors disabled:opacity-50",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60",
              toggle.on
                ? "border-[#FF6B00] bg-[#FF6B00]/10 text-[#FF6B00]"
                : "border-border bg-white text-muted-foreground hover:border-[#FF6B00]/40 hover:text-foreground"
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                toggle.on ? "bg-[#FF6B00]" : "bg-muted-foreground/40"
              )}
              aria-hidden
            />
            {toggle.icon}
            {toggle.label}
          </button>
        ))}
      </div>

      <div
        ref={stageRef}
        style={stageStyle}
        className={cn(
          "relative isolate w-full overflow-hidden rounded-lg border border-border",
          "h-[280px] sm:h-[360px] xl:h-[440px]"
        )}
      >
        {status === "ready" && labelsOn && (
          <LabelOverlay
            ref={overlayRef}
            items={overlayItems}
            highlightedId={highlightedId}
            onHighlight={onHighlight}
            onSelect={handleSelect}
          />
        )}

        {status === "loading" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-g2">
            {/* A pre-rendered still of this machine type, so the panel shows
                the right machine rather than an empty box while it loads. */}
            <img
              src={previewUrlFor(machineType)}
              alt=""
              aria-hidden
              className="max-h-[55%] max-w-[70%] object-contain opacity-70"
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
            <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 size={13} className="animate-spin" />
              Loading model…
            </span>
          </div>
        )}

        {status === "failed" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-g2 px-g4 text-center">
            <Box size={26} className="text-muted-foreground" />
            <p className="text-sm font-semibold text-foreground">3D view unavailable</p>
            <p className="max-w-sm text-xs text-muted-foreground">{message}</p>
          </div>
        )}

        {status === "ready" && (
          <p className="pointer-events-none absolute bottom-2 left-3 text-[10px] text-muted-foreground">
            Drag to rotate, scroll to zoom, right-drag to pan
          </p>
        )}
      </div>

      {status === "ready" && message && (
        <p className="text-xs text-amber-700">{message}</p>
      )}
    </div>
  );
}

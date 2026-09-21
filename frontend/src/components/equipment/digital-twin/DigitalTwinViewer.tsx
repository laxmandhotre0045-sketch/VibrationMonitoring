import React, { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ResolvedTwin, TwinPick } from "@/lib/digital-twin/types";
import {
  BACKGROUND_COLOR,
  buildBearingGroup,
  buildGroundGroup,
  buildMachineGroup,
  buildSensorGroup,
  CAMERA_FOV,
  framingFor,
  disposeObject,
  type CameraViewId,
} from "./twin-scene";
import { cn } from "@/lib/utils";

interface DigitalTwinViewerProps {
  twin: ResolvedTwin;
  /** Pick key of the currently selected marker, if any. */
  selectedKey: string | null;
  onSelect: (pick: TwinPick | null) => void;
  /** Bumping this re-frames the camera on the named view. */
  viewRequest: { view: CameraViewId; nonce: number };
  className?: string;
  /** Rendered instead of the canvas when WebGL is unavailable. */
  fallback: React.ReactNode;
}

/** Distance in px a pointer may travel and still count as a click, not a drag. */
const CLICK_SLOP = 6;

/**
 * The 3D Digital Twin canvas.
 *
 * Renders **on demand** — there is no animation loop. A frame is drawn when
 * the configuration changes, when the camera moves, when the panel resizes or
 * when the selection changes, and at no other time. On an industrial console
 * left open on this page all day that is the difference between an idle GPU
 * and a permanently busy one.
 *
 * The three.js objects live in refs rather than state: React owns the DOM node
 * and the props, three owns the scene graph, and the two only meet in effects.
 */
export function DigitalTwinViewer({
  twin,
  selectedKey,
  onSelect,
  viewRequest,
  className,
  fallback,
}: DigitalTwinViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const frameRef = useRef<number | null>(null);

  const machineGroupRef = useRef<THREE.Group | null>(null);
  const groundGroupRef = useRef<THREE.Group | null>(null);
  const bearingGroupRef = useRef<THREE.Group | null>(null);
  const sensorGroupRef = useRef<THREE.Group | null>(null);

  const [unavailable, setUnavailable] = useState(false);

  /** Schedule exactly one frame, however many times this is called. */
  const requestRender = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const renderer = rendererRef.current;
      const scene = sceneRef.current;
      const camera = cameraRef.current;
      if (renderer && scene && camera) renderer.render(scene, camera);
    });
  }, []);

  // --- Renderer, scene, camera and controls: created once, torn down once ---
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      // No WebGL (blocked, software-blacklisted, headless). The form must stay
      // usable, so hand over to the schematic fallback.
      setUnavailable(true);
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(BACKGROUND_COLOR, 1);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    // `pan-y` rather than `none`: on a phone a vertical swipe over the canvas
    // still scrolls the form, while a horizontal drag orbits the model — which
    // is the axis that matters. `none` would turn the panel into a scroll trap
    // halfway down a six-step form.
    renderer.domElement.style.touchAction = "pan-y";
    renderer.domElement.setAttribute("aria-label", "3D digital twin of the configured machine");
    host.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.add(new THREE.AmbientLight(0xffffff, 1.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(4, 7, 6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.7);
    fill.position.set(-5, 2, -4);
    scene.add(fill);

    const camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1, 0.1, 400);
    camera.position.set(6, 4, 8);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    // No damping: damping needs a continuous loop to settle, which is exactly
    // the idle animation this viewer is built to avoid.
    controls.enableDamping = false;
    controls.enablePan = true;
    controls.rotateSpeed = 0.85;
    controls.zoomSpeed = 0.9;
    controls.addEventListener("change", requestRender);
    // OrbitControls sets `touch-action: none` on attach; put it back.
    renderer.domElement.style.touchAction = "pan-y";
    controlsRef.current = controls;

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width === 0 || height === 0) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      requestRender();
    };
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(host);

    const onContextLost = (event: Event) => {
      event.preventDefault();
      setUnavailable(true);
    };
    renderer.domElement.addEventListener("webglcontextlost", onContextLost);

    return () => {
      renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
      observer.disconnect();
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;

      controls.removeEventListener("change", requestRender);
      controls.dispose();
      controlsRef.current = null;

      disposeObject(machineGroupRef.current);
      disposeObject(groundGroupRef.current);
      disposeObject(bearingGroupRef.current);
      disposeObject(sensorGroupRef.current);
      machineGroupRef.current = null;
      groundGroupRef.current = null;
      bearingGroupRef.current = null;
      sensorGroupRef.current = null;

      scene.clear();
      sceneRef.current = null;
      cameraRef.current = null;

      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      rendererRef.current = null;
    };
  }, [requestRender]);

  // --- The machine: rebuilt only when the machine type selects a new model ---
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    disposeObject(machineGroupRef.current);
    disposeObject(groundGroupRef.current);

    const machine = buildMachineGroup(twin.model);
    const ground = buildGroundGroup(twin.model);
    scene.add(machine, ground);
    machineGroupRef.current = machine;
    groundGroupRef.current = ground;

    requestRender();
  }, [twin.model, requestRender]);

  // --- Bearings and sensors: rebuilt when the configuration changes ---
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    disposeObject(bearingGroupRef.current);
    disposeObject(sensorGroupRef.current);

    const bearings = buildBearingGroup(twin);
    const sensors = buildSensorGroup(twin);
    scene.add(bearings, sensors);
    bearingGroupRef.current = bearings;
    sensorGroupRef.current = sensors;

    requestRender();
  }, [twin, requestRender]);

  // --- Selection highlight ---
  useEffect(() => {
    const groups = [bearingGroupRef.current, sensorGroupRef.current];
    groups.forEach((group) => {
      group?.children.forEach((child) => {
        const pick = child.userData.pick as TwinPick | null | undefined;
        if (!pick) return;

        // Scale relative to the object's own built scale, not to 1: label
        // sprites are sized by their text, so setting a uniform scale would
        // squash every chip into a square on the first deselect.
        let base = child.userData.baseScale as THREE.Vector3 | undefined;
        if (!base) {
          base = child.scale.clone();
          child.userData.baseScale = base;
        }
        const selected = selectedKey !== null && pick.key === selectedKey;
        child.scale.copy(base).multiplyScalar(selected ? 1.5 : 1);
      });
    });
    requestRender();
  }, [selectedKey, twin, requestRender]);

  // --- Named camera views. Also runs on first build, framing the model. ---
  useEffect(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const host = hostRef.current;
    if (!camera || !controls || !host) return;

    const aspect = host.clientHeight > 0 ? host.clientWidth / host.clientHeight : 1.6;
    const framing = framingFor(viewRequest.view, twin.model, aspect);
    camera.position.copy(framing.position);
    controls.target.copy(framing.target);
    controls.minDistance = framing.minDistance;
    controls.maxDistance = framing.maxDistance;
    controls.update();
    requestRender();
  }, [viewRequest, twin.model, requestRender]);

  // --- Picking: a pointerup close to where the pointerdown landed ---
  useEffect(() => {
    const renderer = rendererRef.current;
    const camera = cameraRef.current;
    if (!renderer || !camera) return;

    const element = renderer.domElement;
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downAt: { x: number; y: number } | null = null;

    const onPointerDown = (event: PointerEvent) => {
      downAt = { x: event.clientX, y: event.clientY };
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

      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const targets = [bearingGroupRef.current, sensorGroupRef.current].filter(
        (group): group is THREE.Group => group !== null
      );
      const hits = raycaster.intersectObjects(targets, true);
      const hit = hits.find((entry) => entry.object.userData.pick);
      onSelect((hit?.object.userData.pick as TwinPick | undefined) ?? null);
    };

    element.addEventListener("pointerdown", onPointerDown);
    element.addEventListener("pointerup", onPointerUp);
    return () => {
      element.removeEventListener("pointerdown", onPointerDown);
      element.removeEventListener("pointerup", onPointerUp);
    };
  }, [onSelect, unavailable]);

  if (unavailable) {
    return <div className={cn("relative overflow-hidden", className)}>{fallback}</div>;
  }

  return <div ref={hostRef} className={cn("relative overflow-hidden", className)} />;
}

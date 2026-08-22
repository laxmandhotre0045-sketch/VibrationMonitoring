import React, { useEffect, useId, useRef } from "react";
import { cn } from "@/lib/utils";

const INK = "#07111F";
const DEEP = "#0B1F3A";
const BLUE = "#15366D";
const AMBER = "#D98C00";
const ORANGE = "#FF6B00";
const HEALTHY = "#22C55E";

const FFT_BARS = [
  0.12, 0.28, 0.18, 0.92, 0.74, 0.45, 0.88, 0.52, 0.38, 0.65, 0.42, 0.22, 0.55, 0.3, 0.2, 0.35,
  0.48, 0.62, 0.28, 0.15, 0.4, 0.58, 0.32, 0.24,
];

const SENSOR_NODES = [
  { x: 88, y: 420, r: 3, stroke: ORANGE, ring: 14 },
  { x: 148, y: 380, r: 2.5, stroke: AMBER, ring: 11 },
  { x: 210, y: 445, r: 2.5, stroke: BLUE, ring: 12 },
  { x: 168, y: 490, r: 2, stroke: AMBER, ring: 10 },
  { x: 248, y: 410, r: 3, stroke: ORANGE, ring: 13 },
  { x: 320, y: 460, r: 2.5, stroke: BLUE, ring: 11 },
  { x: 380, y: 395, r: 2, stroke: AMBER, ring: 9 },
  { x: 420, y: 448, r: 2.5, stroke: ORANGE, ring: 12 },
  { x: 480, y: 418, r: 2, stroke: BLUE, ring: 10 },
  { x: 520, y: 472, r: 2.5, stroke: AMBER, ring: 11 },
];

const SENSOR_LINKS: [number, number][] = [
  [0, 1],
  [1, 2],
  [1, 4],
  [2, 3],
  [4, 5],
  [5, 6],
  [5, 7],
  [7, 8],
  [8, 9],
  [2, 5],
];

const WAVES = [
  { y: 340, amp: 22, phase: 0, freqMul: 1, speed: 1.35, opacity: 0.55, stroke: ORANGE, width: 1.2, span: 520, startX: 40 },
  { y: 358, amp: 16, phase: 1.8, freqMul: 1.1, speed: 1.05, opacity: 0.38, stroke: AMBER, width: 0.9, span: 520, startX: 40 },
  { y: 372, amp: 12, phase: 3.4, freqMul: 1.25, speed: 0.85, opacity: 0.28, stroke: BLUE, width: 0.7, span: 520, startX: 40 },
  { y: 388, amp: 9, phase: 5.1, freqMul: 1.4, speed: 0.7, opacity: 0.2, stroke: BLUE, width: 0.6, span: 520, startX: 40 },
  { y: 820, amp: 8, phase: 2.1, freqMul: 1.2, speed: 0.95, opacity: 0.15, stroke: BLUE, width: 0.75, span: 280, startX: 48 },
];

const RIGHT_WAVES = [
  { y: 200, amp: 14, phase: 1.5, freqMul: 1, speed: 1.1, opacity: 0.08, stroke: BLUE, width: 0.75, span: 400, startX: 100 },
  { y: 600, amp: 10, phase: 3.2, freqMul: 1.15, speed: 0.9, opacity: 0.06, stroke: AMBER, width: 0.6, span: 400, startX: 80 },
];

/** Two traveling pulses per sensor link */
const LINK_PULSES = SENSOR_LINKS.flatMap((_, linkIdx) =>
  [0, 0.5].map((offset, pulseIdx) => ({
    linkIdx,
    offset,
    speed: 0.22 + (linkIdx % 4) * 0.04,
    pulseIdx,
  }))
);

function buildWaveformPoints(
  width: number,
  midY: number,
  amplitude: number,
  phase = 0,
  freqMul = 1,
  startX = 0
): string {
  const steps = 180;
  const pts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const x = startX + (i / steps) * width;
    const t = i * 0.16 * freqMul + phase;
    const y =
      midY +
      Math.sin(t) * amplitude +
      Math.sin(t * 2.6) * (amplitude * 0.34) +
      Math.sin(t * 5.8) * (amplitude * 0.12);
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

interface LoginIntelligenceBgProps {
  className?: string;
  variant?: "full" | "left" | "right";
}

/**
 * Login page industrial backdrop — live FFT, scrolling waveforms, sensor mesh pulses.
 */
export function LoginIntelligenceBg({ className, variant = "full" }: LoginIntelligenceBgProps) {
  const gid = useId().replace(/:/g, "");
  const isRight = variant === "right";
  const isLeft = variant === "left" || variant === "full";

  const waveRefs = useRef<(SVGPathElement | null)[]>([]);
  const glowWaveRef = useRef<SVGPathElement | null>(null);
  const rightWaveRefs = useRef<(SVGPathElement | null)[]>([]);
  const linkPulseRefs = useRef<(SVGCircleElement | null)[]>([]);
  const nodeGroupRefs = useRef<(SVGGElement | null)[]>([]);
  const reducedMotionRef = useRef(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedMotionRef.current = mq.matches;
    const onMotionChange = (e: MediaQueryListEvent) => {
      reducedMotionRef.current = e.matches;
    };
    mq.addEventListener("change", onMotionChange);

    let raf = 0;
    const start = performance.now();

    const tick = (now: number) => {
      if (!reducedMotionRef.current) {
        const time = (now - start) / 1000;

        WAVES.forEach((w, i) => {
          const el = waveRefs.current[i];
          if (!el) return;
          el.setAttribute(
            "d",
            buildWaveformPoints(w.span, w.y, w.amp, w.phase + time * w.speed, w.freqMul, w.startX)
          );
        });

        if (glowWaveRef.current) {
          glowWaveRef.current.setAttribute(
            "d",
            buildWaveformPoints(520, 340, 22, time * 1.35, 1, 40)
          );
        }

        RIGHT_WAVES.forEach((w, i) => {
          const el = rightWaveRefs.current[i];
          if (!el) return;
          el.setAttribute(
            "d",
            buildWaveformPoints(w.span, w.y, w.amp, w.phase + time * w.speed, w.freqMul, w.startX)
          );
        });

        LINK_PULSES.forEach((pulse, i) => {
          const el = linkPulseRefs.current[i];
          if (!el) return;
          const [a, b] = SENSOR_LINKS[pulse.linkIdx];
          const na = SENSOR_NODES[a];
          const nb = SENSOR_NODES[b];
          const progress = (time * pulse.speed + pulse.offset) % 1;
          const x = na.x + (nb.x - na.x) * progress;
          const y = na.y + (nb.y - na.y) * progress;
          el.setAttribute("cx", x.toFixed(1));
          el.setAttribute("cy", y.toFixed(1));
          el.setAttribute("opacity", String(0.35 + Math.sin(time * 4 + i) * 0.25));
        });

        SENSOR_NODES.forEach((n, i) => {
          const el = nodeGroupRefs.current[i];
          if (!el) return;
          const bobX = Math.sin(time * 0.55 + i * 1.1) * 1.8;
          const bobY = Math.cos(time * 0.45 + i * 0.9) * 2.2;
          el.setAttribute("transform", `translate(${bobX.toFixed(2)}, ${bobY.toFixed(2)})`);
        });
      }

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      mq.removeEventListener("change", onMotionChange);
    };
  }, []);

  return (
    <div
      className={cn("absolute inset-0 overflow-hidden pointer-events-none select-none", className)}
      aria-hidden
    >
      <div
        className="absolute inset-0"
        style={{
          background: [
            `radial-gradient(ellipse 80% 60% at 20% 50%, rgba(21,54,109,0.45) 0%, transparent 70%)`,
            `radial-gradient(ellipse 50% 80% at 75% 30%, rgba(255,107,0,0.08) 0%, transparent 65%)`,
            `radial-gradient(ellipse 40% 50% at 60% 85%, rgba(217,140,0,0.06) 0%, transparent 60%)`,
            `linear-gradient(145deg, ${INK} 0%, ${DEEP} 42%, ${BLUE} 100%)`,
          ].join(", "),
        }}
      />

      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 600 900"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id={`login-grid-${gid}`} width="28" height="28" patternUnits="userSpaceOnUse">
            <path
              d="M 28 0 L 0 0 0 28"
              fill="none"
              stroke={BLUE}
              strokeWidth="0.5"
              strokeOpacity={isRight ? 0.04 : 0.07}
            />
          </pattern>
          <pattern id={`login-grid-major-${gid}`} width="112" height="112" patternUnits="userSpaceOnUse">
            <rect width="112" height="112" fill={`url(#login-grid-${gid})`} />
            <path
              d="M 112 0 L 0 0 0 112"
              fill="none"
              stroke={BLUE}
              strokeWidth="0.75"
              strokeOpacity={isRight ? 0.055 : 0.09}
            />
          </pattern>
          <linearGradient id={`login-fft-peak-${gid}`} x1="0%" y1="100%" x2="0%" y2="0%">
            <stop offset="0%" stopColor={ORANGE} stopOpacity={0.15} />
            <stop offset="55%" stopColor={AMBER} stopOpacity={0.55} />
            <stop offset="100%" stopColor={ORANGE} stopOpacity={0.95} />
          </linearGradient>
          <linearGradient id={`login-wave-glow-${gid}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={ORANGE} stopOpacity={0} />
            <stop offset="40%" stopColor={ORANGE} stopOpacity={0.35} />
            <stop offset="100%" stopColor={AMBER} stopOpacity={0.12} />
          </linearGradient>
          <filter id={`login-glow-${gid}`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect width="600" height="900" fill={`url(#login-grid-major-${gid})`} />

        {isLeft && (
          <>
            <g transform="translate(300, 520)">
              <circle
                r="48"
                fill="none"
                stroke={ORANGE}
                strokeOpacity={0.12}
                strokeWidth="1"
                className="login-pulse-ring"
              />
              <circle
                r="72"
                fill="none"
                stroke={AMBER}
                strokeOpacity={0.08}
                strokeWidth="0.75"
                className="login-pulse-ring"
                style={{ animationDelay: "4s" }}
              />
              <circle
                r="96"
                fill="none"
                stroke={BLUE}
                strokeOpacity={0.06}
                strokeWidth="0.5"
                className="login-pulse-ring"
                style={{ animationDelay: "8s" }}
              />
              <circle r="4" fill={ORANGE} fillOpacity={0.35} filter={`url(#login-glow-${gid})`} />
              <circle r="8" fill="none" stroke={ORANGE} strokeOpacity={0.2} strokeWidth="0.75" />
            </g>

            <g transform="translate(48, 200)">
              <text
                x="0"
                y="-12"
                fill="white"
                fillOpacity={0.35}
                fontSize="9"
                fontFamily="Inter, sans-serif"
                fontWeight="600"
                letterSpacing="0.08em"
              >
                FFT SPECTRUM
              </text>
              <line x1="0" y1="200" x2="504" y2="200" stroke={BLUE} strokeOpacity={0.25} strokeWidth="0.75" />
              {FFT_BARS.map((h, i) => {
                const maxHeight = 200;
                const barH = h * maxHeight;
                const isPeak = h > 0.7;
                return (
                  <rect
                    key={i}
                    x={i * 21}
                    y={200 - barH}
                    width={isPeak ? 14 : 10}
                    height={barH}
                    rx={1}
                    fill={isPeak ? `url(#login-fft-peak-${gid})` : AMBER}
                    fillOpacity={isPeak ? 1 : 0.22}
                    className={isPeak ? "login-fft-peak" : undefined}
                    style={isPeak ? { animationDelay: `${i * 0.15}s` } : undefined}
                  />
                );
              })}
              {[0, 1, 2, 3, 4].map((t) => (
                <line
                  key={t}
                  x1={t * 126}
                  y1={200}
                  x2={t * 126}
                  y2={206}
                  stroke={BLUE}
                  strokeOpacity={0.3}
                  strokeWidth="0.5"
                />
              ))}
            </g>

            <g className="login-wave-group">
              {WAVES.map((w, i) => (
                <path
                  key={i}
                  ref={(el) => {
                    waveRefs.current[i] = el;
                  }}
                  d={buildWaveformPoints(w.span, w.y, w.amp, w.phase, w.freqMul, w.startX)}
                  fill="none"
                  stroke={w.stroke}
                  strokeOpacity={w.opacity}
                  strokeWidth={w.width}
                  strokeLinecap="round"
                />
              ))}
              <path
                ref={glowWaveRef}
                d={buildWaveformPoints(520, 340, 22, 0, 1, 40)}
                fill="none"
                stroke={`url(#login-wave-glow-${gid})`}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeOpacity={0.25}
              />
            </g>

            <g transform="translate(420, 620)">
              <text
                x="-60"
                y="-50"
                fill="white"
                fillOpacity={0.55}
                fontSize="9"
                fontFamily="Inter, sans-serif"
                fontWeight="600"
                letterSpacing="0.08em"
              >
                MACHINE HEALTH
              </text>
              <path
                d="M -60 0 A 60 60 0 0 1 60 0"
                fill="none"
                stroke={BLUE}
                strokeOpacity={0.2}
                strokeWidth="6"
                strokeLinecap="round"
              />
              <path
                d="M -60 0 A 60 60 0 0 1 -20 -57"
                fill="none"
                stroke={HEALTHY}
                strokeOpacity={0.5}
                strokeWidth="6"
                strokeLinecap="round"
              />
              <path
                d="M -20 -57 A 60 60 0 0 1 35 -48"
                fill="none"
                stroke={AMBER}
                strokeOpacity={0.45}
                strokeWidth="6"
                strokeLinecap="round"
              />
              <path
                d="M 35 -48 A 60 60 0 0 1 60 0"
                fill="none"
                stroke="#EF4444"
                strokeOpacity={0.3}
                strokeWidth="6"
                strokeLinecap="round"
              />
              <g className="login-gauge-needle">
                <line
                  x1="0"
                  y1="0"
                  x2="-28"
                  y2="-46"
                  stroke={ORANGE}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeOpacity={0.85}
                />
              </g>
              <circle r="4" fill={ORANGE} fillOpacity={0.6} />
              <text
                x="-18"
                y="22"
                fill="white"
                fillOpacity={0.88}
                fontSize="18"
                fontFamily="Inter, sans-serif"
                fontWeight="700"
              >
                87
              </text>
              <text x="8" y="22" fill="white" fillOpacity={0.5} fontSize="10" fontFamily="Inter, sans-serif">
                /100
              </text>
            </g>

            <g>
              {SENSOR_LINKS.map(([a, b], i) => (
                <g key={i}>
                  <line
                    x1={SENSOR_NODES[a].x}
                    y1={SENSOR_NODES[a].y}
                    x2={SENSOR_NODES[b].x}
                    y2={SENSOR_NODES[b].y}
                    stroke={AMBER}
                    strokeOpacity={0.1}
                    strokeWidth="0.75"
                  />
                  <line
                    x1={SENSOR_NODES[a].x}
                    y1={SENSOR_NODES[a].y}
                    x2={SENSOR_NODES[b].x}
                    y2={SENSOR_NODES[b].y}
                    stroke={ORANGE}
                    strokeOpacity={0.22}
                    strokeWidth="1"
                    strokeDasharray="3 14"
                    className="login-sensor-link-flow"
                    style={{ animationDelay: `${i * 0.35}s` }}
                  />
                </g>
              ))}

              {LINK_PULSES.map((pulse, i) => (
                <circle
                  key={`pulse-${pulse.linkIdx}-${pulse.pulseIdx}`}
                  ref={(el) => {
                    linkPulseRefs.current[i] = el;
                  }}
                  cx={SENSOR_NODES[SENSOR_LINKS[pulse.linkIdx][0]].x}
                  cy={SENSOR_NODES[SENSOR_LINKS[pulse.linkIdx][0]].y}
                  r={2.2}
                  fill={ORANGE}
                  fillOpacity={0.65}
                  filter={`url(#login-glow-${gid})`}
                />
              ))}

              {SENSOR_NODES.map((n, i) => (
                <g
                  key={i}
                  ref={(el) => {
                    nodeGroupRefs.current[i] = el;
                  }}
                >
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={n.ring}
                    fill="none"
                    stroke={n.stroke}
                    strokeOpacity={0.06}
                    strokeWidth="0.5"
                    className="login-sensor-ring"
                    style={{ animationDelay: `${i * 0.5}s` }}
                  />
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={n.r}
                    fill={n.stroke}
                    fillOpacity={0.35}
                    className="login-sensor-node"
                    style={{ animationDelay: `${i * 0.6}s` }}
                  />
                </g>
              ))}
            </g>

            <g transform="translate(48, 720)">
              <rect
                x="0"
                y="0"
                width="504"
                height="56"
                rx="6"
                fill={DEEP}
                fillOpacity={0.5}
                stroke={BLUE}
                strokeOpacity={0.3}
                strokeWidth="0.75"
              />
              {[
                { label: "RPM", value: "1,847", x: 16 },
                { label: "VEL mm/s", value: "2.4", x: 148 },
                { label: "TEMP °C", value: "68.2", x: 280 },
                { label: "STATUS", value: "NORMAL", x: 400, accent: HEALTHY },
              ].map((m) => (
                <g key={m.label} transform={`translate(${m.x}, 12)`}>
                  <text
                    fill="white"
                    fillOpacity={0.35}
                    fontSize="8"
                    fontFamily="Inter, sans-serif"
                    fontWeight="600"
                    letterSpacing="0.06em"
                  >
                    {m.label}
                  </text>
                  <text
                    x="0"
                    y="22"
                    fill={m.accent ?? "white"}
                    fillOpacity={m.accent ? 0.9 : 0.75}
                    fontSize="14"
                    fontFamily="Inter, sans-serif"
                    fontWeight="700"
                  >
                    {m.value}
                  </text>
                </g>
              ))}
            </g>
          </>
        )}

        {isRight && (
          <>
            {RIGHT_WAVES.map((w, i) => (
              <path
                key={i}
                ref={(el) => {
                  rightWaveRefs.current[i] = el;
                }}
                d={buildWaveformPoints(w.span, w.y, w.amp, w.phase, w.freqMul, w.startX)}
                fill="none"
                stroke={w.stroke}
                strokeOpacity={w.opacity}
                strokeWidth={w.width}
                strokeLinecap="round"
              />
            ))}
            <circle
              cx="480"
              cy="400"
              r="60"
              fill="none"
              stroke={ORANGE}
              strokeOpacity={0.04}
              strokeWidth="0.75"
              className="login-pulse-ring"
            />
            <circle
              cx="480"
              cy="400"
              r="90"
              fill="none"
              stroke={BLUE}
              strokeOpacity={0.03}
              strokeWidth="0.5"
              className="login-pulse-ring"
              style={{ animationDelay: "6s" }}
            />
          </>
        )}
      </svg>

      {!isRight && (
        <div
          className="absolute inset-0"
          style={{
            background: [
              "linear-gradient(90deg, rgba(7,17,31,0.55) 0%, transparent 50%)",
              "linear-gradient(180deg, rgba(7,17,31,0.45) 0%, transparent 20%, rgba(7,17,31,0.2) 70%, rgba(7,17,31,0.45) 100%)",
            ].join(", "),
          }}
        />
      )}

      {isRight && (
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(270deg, rgba(7,17,31,0.4) 0%, transparent 40%, rgba(11,31,58,0.25) 100%)",
          }}
        />
      )}
    </div>
  );
}

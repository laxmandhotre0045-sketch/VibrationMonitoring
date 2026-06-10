import React, { useId } from "react";
import { cn } from "@/lib/utils";

const BLUE = "#15366D";
const AMBER = "#D98C00";
const ORANGE = "#FF6B00";

/** Wrapper class — use on the decorative layer inside header/hero shells */
export const heroIntelligenceBgClass =
  "absolute inset-0 overflow-hidden pointer-events-none select-none";

const FFT_BARS = [
  0.15, 0.35, 0.22, 0.72, 0.48, 0.3, 0.58, 0.4, 0.32, 0.5, 0.28, 0.2, 0.38, 0.25, 0.18, 0.3,
];

function buildWaveformPoints(
  width: number,
  midY: number,
  amplitude: number,
  phase = 0,
  freqMul = 1
): string {
  const steps = 160;
  const pts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const x = (i / steps) * width;
    const t = i * 0.18 * freqMul + phase;
    const y =
      midY +
      Math.sin(t) * amplitude +
      Math.sin(t * 2.4) * (amplitude * 0.32) +
      Math.sin(t * 5.2) * (amplitude * 0.1);
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

/** Sensor mesh — nodes and connection lines (monitoring / connectivity) */
const SENSOR_NODES = [
  { x: 560, y: 48, r: 2.5, stroke: AMBER, fillOpacity: 0.14, ring: 10 },
  { x: 620, y: 72, r: 2, stroke: BLUE, fillOpacity: 0.11, ring: 8 },
  { x: 680, y: 42, r: 2.5, stroke: AMBER, fillOpacity: 0.13, ring: 11 },
  { x: 640, y: 98, r: 2, stroke: BLUE, fillOpacity: 0.1, ring: 9 },
  { x: 720, y: 68, r: 2.5, stroke: AMBER, fillOpacity: 0.12, ring: 10 },
  { x: 748, y: 38, r: 1.8, stroke: BLUE, fillOpacity: 0.09, ring: 7 },
];

const SENSOR_LINKS: [number, number][] = [
  [0, 1],
  [1, 2],
  [1, 3],
  [2, 4],
  [3, 4],
  [4, 5],
];

interface HeroIntelligenceBgProps {
  className?: string;
}

/**
 * Premium header/hero backdrop — waves, sensor mesh, FFT, orange depth.
 * Use ONLY inside page headers and hero sections (PageHero, DigitalTwinHeader).
 */
export function HeroIntelligenceBg({ className }: HeroIntelligenceBgProps) {
  const gid = useId().replace(/:/g, "");

  return (
    <div className={cn(heroIntelligenceBgClass, className)} aria-hidden>
      {/* Orange depth washes */}
      <div
        className="absolute inset-0"
        style={{
          background: [
            "radial-gradient(ellipse 55% 90% at 88% 45%, rgba(255,107,0,0.07) 0%, transparent 68%)",
            "radial-gradient(ellipse 35% 70% at 12% 85%, rgba(217,140,0,0.045) 0%, transparent 62%)",
            "linear-gradient(105deg, transparent 40%, rgba(255,178,107,0.04) 72%, transparent 92%)",
          ].join(", "),
        }}
      />

      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 800 160"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id={`hero-grid-${gid}`} width="32" height="32" patternUnits="userSpaceOnUse">
            <path
              d="M 32 0 L 0 0 0 32"
              fill="none"
              stroke={BLUE}
              strokeWidth="0.5"
              strokeOpacity={0.038}
            />
          </pattern>
          <pattern id={`hero-grid-major-${gid}`} width="128" height="128" patternUnits="userSpaceOnUse">
            <rect width="128" height="128" fill={`url(#hero-grid-${gid})`} />
            <path
              d="M 128 0 L 0 0 0 128"
              fill="none"
              stroke={BLUE}
              strokeWidth="0.75"
              strokeOpacity={0.052}
            />
          </pattern>
          <linearGradient id={`hero-wave-fade-${gid}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={BLUE} stopOpacity={0.02} />
            <stop offset="35%" stopColor={BLUE} stopOpacity={0.08} />
            <stop offset="100%" stopColor={BLUE} stopOpacity={0.04} />
          </linearGradient>
        </defs>

        <rect width="800" height="160" fill={`url(#hero-grid-major-${gid})`} />

        {/* Soft geometric depth — monitoring focal rings */}
        <circle cx="670" cy="78" r="36" fill="none" stroke={AMBER} strokeOpacity={0.045} strokeWidth="0.75" />
        <circle cx="670" cy="78" r="54" fill="none" stroke={BLUE} strokeOpacity={0.032} strokeWidth="0.5" />
        <circle cx="670" cy="78" r="72" fill="none" stroke={ORANGE} strokeOpacity={0.025} strokeWidth="0.5" />
        <path
          d="M 520 120 Q 600 40 760 55"
          fill="none"
          stroke={AMBER}
          strokeOpacity={0.035}
          strokeWidth="0.5"
          strokeDasharray="4 6"
        />

        {/* Multi-layer wave stack */}
        <g>
          {[
            { y: 58, amp: 10, phase: 3.2, freqMul: 0.9, opacity: 0.048, stroke: BLUE },
            { y: 72, amp: 18, phase: 0, freqMul: 1, opacity: 0.09, stroke: BLUE },
            { y: 88, amp: 13, phase: 1.4, freqMul: 1.15, opacity: 0.072, stroke: AMBER },
            { y: 104, amp: 9, phase: 2.8, freqMul: 1.25, opacity: 0.058, stroke: AMBER },
            { y: 118, amp: 7, phase: 4.1, freqMul: 1.1, opacity: 0.042, stroke: BLUE },
          ].map((t, i) => (
            <path
              key={i}
              d={buildWaveformPoints(740, t.y, t.amp, t.phase, t.freqMul)}
              fill="none"
              stroke={t.stroke}
              strokeOpacity={t.opacity}
              strokeWidth={i === 1 ? 0.85 : 0.65}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </g>

        {/* Sensor connectivity mesh */}
        <g>
          {SENSOR_LINKS.map(([a, b], i) => (
            <line
              key={i}
              x1={SENSOR_NODES[a].x}
              y1={SENSOR_NODES[a].y}
              x2={SENSOR_NODES[b].x}
              y2={SENSOR_NODES[b].y}
              stroke={AMBER}
              strokeOpacity={0.055}
              strokeWidth="0.5"
            />
          ))}
          {SENSOR_NODES.map((n, i) => (
            <g key={i}>
              <circle cx={n.x} cy={n.y} r={n.ring} fill="none" stroke={n.stroke} strokeOpacity={0.04} strokeWidth="0.5" />
              <circle cx={n.x} cy={n.y} r={n.r} fill={n.stroke} fillOpacity={n.fillOpacity} />
              <circle cx={n.x} cy={n.y} r={n.r + 1.2} fill="none" stroke={n.stroke} strokeOpacity={0.08} strokeWidth="0.5" />
            </g>
          ))}
        </g>

        {/* FFT spectrum — data intelligence accent */}
        <g transform="translate(600, 28)">
          {FFT_BARS.slice(0, 16).map((h, i) => {
            const maxHeight = 64;
            const barH = h * maxHeight;
            const barOpacity = 0.068;
            return (
              <rect
                key={i}
                x={i * 7}
                y={maxHeight - barH}
                width={4}
                height={barH}
                rx={0.5}
                fill={AMBER}
                fillOpacity={i === 3 || i === 6 ? barOpacity * 1.12 : barOpacity}
              />
            );
          })}
          <line x1="0" y1={64} x2={112} y2={64} stroke={BLUE} strokeOpacity={0.04} strokeWidth="0.5" />
        </g>

        {/* Left-side subtle telemetry trace */}
        <path
          d={buildWaveformPoints(220, 128, 6, 1.2, 1.3)}
          fill="none"
          stroke={BLUE}
          strokeOpacity={0.04}
          strokeWidth="0.5"
          strokeLinecap="round"
        />
      </svg>

      {/* Content protection — keeps title/breadcrumbs readable */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(90deg, rgba(255,253,248,0.88) 0%, rgba(255,253,248,0.42) 38%, transparent 58%, rgba(255,253,248,0.55) 100%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(255,253,248,0.78) 0%, transparent 42%, rgba(255,253,248,0.75) 100%)",
        }}
      />
    </div>
  );
}

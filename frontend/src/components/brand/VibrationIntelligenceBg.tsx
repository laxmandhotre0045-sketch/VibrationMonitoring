import React, { useId } from "react";
import { cn } from "@/lib/utils";

const BLUE = "#15366D";
const AMBER = "#D98C00";

/** Deterministic accelerometer-style time waveform */
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

/** Compact FFT harmonic peaks */
const FFT_BARS = [
  0.15, 0.35, 0.22, 0.72, 0.48, 0.3, 0.58, 0.4, 0.32, 0.5, 0.28, 0.2, 0.38, 0.25, 0.18, 0.3,
];

interface VibrationIntelligenceBgProps {
  className?: string;
  /** hero = header band; page = full Equipment Master canvas */
  variant?: "hero" | "page";
}

function EngineeringGrid({ gid, opacity = 0.025 }: { gid: string; opacity?: number }) {
  return (
    <defs>
      <pattern id={`grid-${gid}`} width="32" height="32" patternUnits="userSpaceOnUse">
        <path
          d="M 32 0 L 0 0 0 32"
          fill="none"
          stroke={BLUE}
          strokeWidth="0.5"
          strokeOpacity={opacity}
        />
      </pattern>
      <pattern id={`grid-major-${gid}`} width="128" height="128" patternUnits="userSpaceOnUse">
        <rect width="128" height="128" fill={`url(#grid-${gid})`} />
        <path
          d="M 128 0 L 0 0 0 128"
          fill="none"
          stroke={BLUE}
          strokeWidth="0.75"
          strokeOpacity={opacity * 1.4}
        />
      </pattern>
    </defs>
  );
}

function FftSpectrum({ x, y, barCount = 16, maxHeight = 56, barOpacity = 0.05 }: {
  x: number;
  y: number;
  barCount?: number;
  maxHeight?: number;
  barOpacity?: number;
}) {
  const bars = FFT_BARS.slice(0, barCount);
  return (
    <g transform={`translate(${x}, ${y})`}>
      {bars.map((h, i) => {
        const barH = h * maxHeight;
        return (
          <rect
            key={i}
            x={i * 7}
            y={maxHeight - barH}
            width={4}
            height={barH}
            rx={0.5}
            fill={AMBER}
            fillOpacity={i === 3 || i === 6 ? barOpacity * 1.15 : barOpacity}
          />
        );
      })}
      <line
        x1="0"
        y1={maxHeight}
        x2={bars.length * 7}
        y2={maxHeight}
        stroke={BLUE}
        strokeOpacity={0.03}
        strokeWidth="0.5"
      />
    </g>
  );
}

function WaveformLayer({
  width,
  traces,
}: {
  width: number;
  traces: { y: number; amp: number; phase?: number; freqMul?: number; opacity?: number }[];
}) {
  return (
    <g>
      {traces.map((t, i) => (
        <path
          key={i}
          d={buildWaveformPoints(width, t.y, t.amp, t.phase ?? i * 0.8, t.freqMul ?? 1)}
          fill="none"
          stroke={BLUE}
          strokeOpacity={t.opacity ?? 0.065}
          strokeWidth="0.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </g>
  );
}

/**
 * Subtle engineering backdrop — grid, oscilloscope traces, FFT spectrum.
 * Decorative only; must not compete with form content.
 */
export function VibrationIntelligenceBg({ className, variant = "hero" }: VibrationIntelligenceBgProps) {
  const gid = useId().replace(/:/g, "");

  if (variant === "page") {
    return (
      <div
        className={cn(
          "pointer-events-none select-none overflow-hidden",
          className
        )}
        aria-hidden
      >
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox="0 0 1200 900"
          preserveAspectRatio="xMidYMid slice"
          xmlns="http://www.w3.org/2000/svg"
        >
          <EngineeringGrid gid={gid} opacity={0.022} />
          <rect width="1200" height="900" fill={`url(#grid-major-${gid})`} />

          <WaveformLayer
            width={1100}
            traces={[
              { y: 180, amp: 14, phase: 0, opacity: 0.055 },
              { y: 420, amp: 10, phase: 2.1, freqMul: 1.15, opacity: 0.05 },
              { y: 660, amp: 12, phase: 4.3, opacity: 0.06 },
            ]}
          />

          <FftSpectrum x={1020} y={120} barCount={14} maxHeight={48} barOpacity={0.045} />
          <FftSpectrum x={1040} y={520} barCount={10} maxHeight={36} barOpacity={0.04} />
        </svg>

        {/* Center wash — keeps form area calm */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 75% 60% at 42% 45%, #FFFDF8 0%, rgba(255,253,248,0.92) 45%, rgba(255,253,248,0.55) 100%)",
          }}
        />
      </div>
    );
  }

  /* Hero variant — DigitalTwinHeader & PageHero */
  return (
    <div className={cn("absolute inset-0 overflow-hidden pointer-events-none select-none", className)} aria-hidden>
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 800 160"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <EngineeringGrid gid={gid} opacity={0.025} />
        <rect width="800" height="160" fill={`url(#grid-major-${gid})`} />

        <WaveformLayer
          width={720}
          traces={[
            { y: 72, amp: 18, phase: 0, opacity: 0.07 },
            { y: 98, amp: 11, phase: 1.6, freqMul: 1.2, opacity: 0.055 },
          ]}
        />

        <FftSpectrum x={620} y={36} barCount={16} maxHeight={64} barOpacity={0.05} />
      </svg>

      <div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(90deg, #FFFDF8 0%, transparent 22%, transparent 78%, #FFFDF8 100%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(180deg, #FFFDF8 0%, transparent 40%, #FFFDF8 100%)",
        }}
      />
    </div>
  );
}

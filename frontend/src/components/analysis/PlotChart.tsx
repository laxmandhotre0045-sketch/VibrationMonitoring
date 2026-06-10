import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ZoomIn,
  ZoomOut,
  ScanSearch,
  Move,
  Maximize2,
  RotateCcw,
} from "lucide-react";
import type { PlotSeries } from "@/types/measurements";
import { cn } from "@/lib/utils";

interface PlotChartProps {
  plot: PlotSeries;
  height?: number;
}

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

const WIDTH = 600;
const PAD = 40;
const PLOT_W = WIDTH - PAD * 2;
const ZOOM_FACTOR = 0.75;

type InteractionMode = "pan" | "zoom";

function downsample(x: number[], y: number[], maxPoints = 1200): { x: number[]; y: number[] } {
  if (x.length <= maxPoints) return { x, y };
  const step = Math.ceil(x.length / maxPoints);
  return {
    x: x.filter((_, i) => i % step === 0),
    y: y.filter((_, i) => i % step === 0),
  };
}

function computeDataBounds(x: number[], y: number[], isOrbit: boolean): Bounds {
  if (!x.length) return { minX: 0, maxX: 1, minY: 0, maxY: 1 };

  let minX = Math.min(...x);
  let maxX = Math.max(...x);
  let minY = Math.min(...y);
  let maxY = Math.max(...y);

  if (isOrbit) {
    const limit = Math.max(Math.abs(minX), Math.abs(maxX), Math.abs(minY), Math.abs(maxY), 0.001);
    minX = -limit;
    maxX = limit;
    minY = -limit;
    maxY = limit;
  }

  return padBounds({ minX, maxX, minY, maxY });
}

function padBounds(b: Bounds, factor = 0.05): Bounds {
  const rangeX = b.maxX - b.minX || 1;
  const rangeY = b.maxY - b.minY || 1;
  const px = rangeX * factor;
  const py = rangeY * factor;
  return {
    minX: b.minX - px,
    maxX: b.maxX + px,
    minY: b.minY - py,
    maxY: b.maxY + py,
  };
}

function zoomBounds(b: Bounds, scale: number, anchor?: { x: number; y: number }): Bounds {
  const cx = anchor?.x ?? (b.minX + b.maxX) / 2;
  const cy = anchor?.y ?? (b.minY + b.maxY) / 2;
  const halfX = ((b.maxX - b.minX) / 2) * scale;
  const halfY = ((b.maxY - b.minY) / 2) * scale;
  return {
    minX: cx - halfX,
    maxX: cx + halfX,
    minY: cy - halfY,
    maxY: cy + halfY,
  };
}

function panBounds(b: Bounds, dx: number, dy: number): Bounds {
  return {
    minX: b.minX + dx,
    maxX: b.maxX + dx,
    minY: b.minY + dy,
    maxY: b.maxY + dy,
  };
}

function dataToSvg(x: number, y: number, view: Bounds, plotH: number): { px: number; py: number } {
  const rangeX = view.maxX - view.minX || 1;
  const rangeY = view.maxY - view.minY || 1;
  return {
    px: PAD + ((x - view.minX) / rangeX) * PLOT_W,
    py: plotH - PAD - ((y - view.minY) / rangeY) * (plotH - PAD * 2),
  };
}

function svgToData(px: number, py: number, view: Bounds, plotH: number): { x: number; y: number } {
  const rangeX = view.maxX - view.minX || 1;
  const rangeY = view.maxY - view.minY || 1;
  return {
    x: view.minX + ((px - PAD) / PLOT_W) * rangeX,
    y: view.minY + ((plotH - PAD - py) / (plotH - PAD * 2)) * rangeY,
  };
}

function ToolButton({
  onClick,
  active,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "rounded p-1.5 transition-colors",
        active
          ? "bg-blue-100 text-blue-700"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"
      )}
    >
      {children}
    </button>
  );
}

export function PlotChart({ plot, height = 220 }: PlotChartProps) {
  const plotStyle = (plot.metadata?.plot_style as string) || "line";
  const isOrbit = plotStyle === "orbit";
  const plotH = height;
  const plotAreaH = plotH - PAD * 2;

  const { x: dataX, y: dataY } = useMemo(
    () => downsample(plot.x, plot.y),
    [plot.x, plot.y]
  );

  const dataBounds = useMemo(
    () => computeDataBounds(dataX, dataY, isOrbit),
    [dataX, dataY, isOrbit]
  );

  const [viewBounds, setViewBounds] = useState<Bounds>(dataBounds);
  const [mode, setMode] = useState<InteractionMode>("pan");
  const [selectionRect, setSelectionRect] = useState<{
    x: number;
    y: number;
    w: number;
    h: number;
  } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const dragRef = useRef<{
    type: "pan" | "zoom";
    startPx: number;
    startPy: number;
    startBounds: Bounds;
  } | null>(null);

  useEffect(() => {
    setViewBounds(dataBounds);
  }, [dataBounds, plot.plot_type, plot.channel]);

  const autoscale = useCallback(() => setViewBounds(dataBounds), [dataBounds]);
  const resetAxis = useCallback(() => setViewBounds(padBounds(dataBounds)), [dataBounds]);
  const zoomIn = useCallback(
    () => setViewBounds((v) => zoomBounds(v, ZOOM_FACTOR)),
    []
  );
  const zoomOut = useCallback(
    () => setViewBounds((v) => zoomBounds(v, 1 / ZOOM_FACTOR)),
    []
  );

  const getSvgPoint = (e: React.MouseEvent | WheelEvent): { px: number; py: number } | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const scaleY = plotH / rect.height;
    return {
      px: (e.clientX - rect.left) * scaleX,
      py: (e.clientY - rect.top) * scaleY,
    };
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const pt = getSvgPoint(e);
    if (!pt) return;
    if (pt.px < PAD || pt.px > WIDTH - PAD || pt.py < PAD || pt.py > plotH - PAD) return;

    const anchor = svgToData(pt.px, pt.py, viewBounds, plotH);
    const scale = e.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR;
    setViewBounds((v) => zoomBounds(v, scale, anchor));
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const pt = getSvgPoint(e);
    if (!pt) return;
    if (pt.px < PAD || pt.px > WIDTH - PAD || pt.py < PAD || pt.py > plotH - PAD) return;

    dragRef.current = {
      type: mode,
      startPx: pt.px,
      startPy: pt.py,
      startBounds: viewBounds,
    };
  };

  const onMouseMove = (e: React.MouseEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const pt = getSvgPoint(e);
    if (!pt) return;

    if (drag.type === "pan") {
      const rangeX = drag.startBounds.maxX - drag.startBounds.minX;
      const rangeY = drag.startBounds.maxY - drag.startBounds.minY;
      const dx = -((pt.px - drag.startPx) / PLOT_W) * rangeX;
      const dy = ((pt.py - drag.startPy) / plotAreaH) * rangeY;
      setViewBounds(panBounds(drag.startBounds, dx, dy));
    } else {
      setSelectionRect({
        x: Math.min(drag.startPx, pt.px),
        y: Math.min(drag.startPy, pt.py),
        w: Math.abs(pt.px - drag.startPx),
        h: Math.abs(pt.py - drag.startPy),
      });
    }
  };

  const onMouseUp = (e: React.MouseEvent) => {
    const drag = dragRef.current;
    if (!drag) return;

    if (drag.type === "zoom") {
      const pt = getSvgPoint(e);
      if (pt) {
        const x1 = Math.max(PAD, Math.min(drag.startPx, pt.px));
        const x2 = Math.min(WIDTH - PAD, Math.max(drag.startPx, pt.px));
        const y1 = Math.max(PAD, Math.min(drag.startPy, pt.py));
        const y2 = Math.min(plotH - PAD, Math.max(drag.startPy, pt.py));

        if (x2 - x1 > 8 && y2 - y1 > 8) {
          const d1 = svgToData(x1, y2, drag.startBounds, plotH);
          const d2 = svgToData(x2, y1, drag.startBounds, plotH);
          setViewBounds({
            minX: Math.min(d1.x, d2.x),
            maxX: Math.max(d1.x, d2.x),
            minY: Math.min(d1.y, d2.y),
            maxY: Math.max(d1.y, d2.y),
          });
        }
      }
      setSelectionRect(null);
    }
    dragRef.current = null;
  };

  const { path, fillPath } = useMemo(() => {
    if (!dataX.length) {
      return { path: "", fillPath: "" };
    }

    const points = dataX.map((xv, i) => {
      const { px, py } = dataToSvg(xv, dataY[i], viewBounds, plotH);
      return `${px},${py}`;
    });

    const linePath = `M ${points.join(" L ")}`;
    const lastX = dataToSvg(dataX[dataX.length - 1], dataY[dataY.length - 1], viewBounds, plotH).px;
    const areaPath = isOrbit
      ? ""
      : `${linePath} L ${lastX},${plotH - PAD} L ${PAD},${plotH - PAD} Z`;

    return { path: linePath, fillPath: areaPath };
  }, [dataX, dataY, viewBounds, plotH, isOrbit]);

  const orbitRadius = plotAreaH / 2;
  const cx = WIDTH / 2;
  const cy = plotH / 2;

  const gridLines = useMemo(() => {
    const lines: { x1: number; y1: number; x2: number; y2: number }[] = [];
    for (let i = 0; i <= 4; i++) {
      const frac = i / 4;
      const x = PAD + frac * PLOT_W;
      const y = PAD + frac * plotAreaH;
      lines.push({ x1: x, y1: PAD, x2: x, y2: plotH - PAD });
      lines.push({ x1: PAD, y1: y, x2: WIDTH - PAD, y2: y });
    }
    return lines;
  }, [plotAreaH]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">{plot.title}</h3>
        <div className="flex items-center gap-0.5">
          <ToolButton onClick={zoomIn} title="Zoom in">
            <ZoomIn className="h-3.5 w-3.5" />
          </ToolButton>
          <ToolButton onClick={zoomOut} title="Zoom out">
            <ZoomOut className="h-3.5 w-3.5" />
          </ToolButton>
          <ToolButton
            onClick={() => setMode("zoom")}
            active={mode === "zoom"}
            title="Box zoom — drag to select area"
          >
            <ScanSearch className="h-3.5 w-3.5" />
          </ToolButton>
          <ToolButton
            onClick={() => setMode("pan")}
            active={mode === "pan"}
            title="Pan — drag to move"
          >
            <Move className="h-3.5 w-3.5" />
          </ToolButton>
          <ToolButton onClick={autoscale} title="Autoscale — fit all data">
            <Maximize2 className="h-3.5 w-3.5" />
          </ToolButton>
          <ToolButton onClick={resetAxis} title="Reset axis">
            <RotateCcw className="h-3.5 w-3.5" />
          </ToolButton>
          <span className="ml-1 text-xs text-slate-500">ch{plot.channel}</span>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${plotH}`}
        className={cn(
          "w-full select-none rounded border border-slate-100",
          mode === "pan" ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair"
        )}
        role="img"
        aria-label={plot.title}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => {
          dragRef.current = null;
          setSelectionRect(null);
        }}
      >
        <defs>
          <linearGradient id={`grad-${plot.plot_type}-${plot.channel}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        <rect x={PAD} y={PAD} width={PLOT_W} height={plotAreaH} fill="#f8fafc" stroke="#e2e8f0" />

        {gridLines.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="#eef2f7" strokeWidth="1" />
        ))}

        {isOrbit && (
          <>
            <line x1={cx - orbitRadius} y1={cy} x2={cx + orbitRadius} y2={cy} stroke="#e2e8f0" />
            <line x1={cx} y1={cy - orbitRadius} x2={cx} y2={cy + orbitRadius} stroke="#e2e8f0" />
            <circle cx={cx} cy={cy} r={orbitRadius} fill="none" stroke="#e2e8f0" strokeDasharray="4 4" />
          </>
        )}

        <clipPath id={`clip-${plot.plot_type}-${plot.channel}`}>
          <rect x={PAD} y={PAD} width={PLOT_W} height={plotAreaH} />
        </clipPath>

        <g clipPath={`url(#clip-${plot.plot_type}-${plot.channel})`}>
          {!isOrbit && fillPath && (
            <path d={fillPath} fill={`url(#grad-${plot.plot_type}-${plot.channel})`} />
          )}
          {path && <path d={path} fill="none" stroke="#2563eb" strokeWidth="1.5" />}
        </g>

        {selectionRect && (
          <rect
            x={selectionRect.x}
            y={selectionRect.y}
            width={selectionRect.w}
            height={selectionRect.h}
            fill="rgba(37,99,235,0.1)"
            stroke="#2563eb"
            strokeWidth="1"
            strokeDasharray="4 2"
          />
        )}

        <text x={WIDTH / 2} y={plotH - 8} textAnchor="middle" className="fill-slate-500 text-[10px]">
          {plot.x_label}
        </text>
        <text
          x="12"
          y={plotH / 2}
          textAnchor="middle"
          transform={`rotate(-90 12 ${plotH / 2})`}
          className="fill-slate-500 text-[10px]"
        >
          {plot.y_label}
        </text>
      </svg>

      <p className="mt-1 text-[10px] text-slate-400">
        View X: {viewBounds.minX.toFixed(4)} – {viewBounds.maxX.toFixed(4)} · Y:{" "}
        {viewBounds.minY.toFixed(4)} – {viewBounds.maxY.toFixed(4)} · Scroll to zoom ·{" "}
        {mode === "pan" ? "Drag to pan" : "Drag to box-zoom"}
      </p>
    </div>
  );
}

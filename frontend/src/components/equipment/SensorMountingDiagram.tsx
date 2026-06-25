import React from "react";

interface SensorMountingDiagramProps {
  orientations?: Record<string, string>;
}

export function SensorMountingDiagram({ orientations = {} }: SensorMountingDiagramProps) {
  const getColor = (location: string) => {
    if (orientations[location]) return "#2563eb";
    return "#d1d5db";
  };

  return (
    <div className="flex flex-col items-center">
      <p className="text-overline mb-3">Mounting Orientation Reference</p>
      <svg viewBox="0 0 320 200" className="w-full max-w-xs" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Motor body (NDE side) */}
        <rect x="10" y="70" width="100" height="60" rx="6" fill="#e8f0fe" stroke="#93c5fd" strokeWidth="1.5" />
        <text x="60" y="104" textAnchor="middle" fontSize="11" fontWeight="600" fill="#1e40af">NDE</text>

        {/* Shaft */}
        <rect x="110" y="94" width="100" height="12" rx="2" fill="#bfdbfe" stroke="#93c5fd" strokeWidth="1" />

        {/* Pump/Load body (DE side) */}
        <rect x="210" y="70" width="100" height="60" rx="6" fill="#fef3c7" stroke="#fbbf24" strokeWidth="1.5" />
        <text x="260" y="104" textAnchor="middle" fontSize="11" fontWeight="600" fill="#92400e">DE</text>

        {/* NDE Vertical arrow */}
        <line x1="60" y1="65" x2="60" y2="30" stroke={getColor("DE Vertical")} strokeWidth="2" markerEnd="url(#arrowBlue)" />
        <text x="63" y="25" fontSize="9" fill={getColor("DE Vertical")} fontWeight="500">Vertical</text>

        {/* DE Vertical arrow */}
        <line x1="260" y1="65" x2="260" y2="30" stroke={getColor("NDE Vertical")} strokeWidth="2" markerEnd="url(#arrowBlue)" />
        <text x="263" y="25" fontSize="9" fill={getColor("NDE Vertical")} fontWeight="500">Vertical</text>

        {/* Axial arrow */}
        <line x1="320" y1="100" x2="285" y2="100" stroke={getColor("DE Axial")} strokeWidth="2" markerEnd="url(#arrowOrange)" />
        <text x="293" y="93" fontSize="9" fill={getColor("DE Axial")} fontWeight="500">Axial</text>

        {/* NDE Horizontal arrow */}
        <line x1="5" y1="100" x2="40" y2="100" stroke={getColor("NDE Horizontal")} strokeWidth="2" markerEnd="url(#arrowBlue)" />
        <text x="0" y="118" fontSize="9" fill={getColor("NDE Horizontal")} fontWeight="500">H</text>

        {/* DE Horizontal arrow */}
        <line x1="210" y1="145" x2="210" y2="170" stroke={getColor("DE Horizontal")} strokeWidth="2" markerEnd="url(#arrowOrange)" />
        <text x="215" y="183" fontSize="9" fill={getColor("DE Horizontal")} fontWeight="500">Horizontal</text>

        {/* NDE Axial arrow from shaft */}
        <line x1="100" y1="100" x2="65" y2="100" stroke={getColor("NDE Axial")} strokeWidth="2" markerEnd="url(#arrowNDEAxial)" />
        <text x="70" y="93" fontSize="9" fill={getColor("NDE Axial")} fontWeight="500">Axial</text>

        {/* Arrow markers */}
        <defs>
          <marker id="arrowBlue" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#2563eb" />
          </marker>
          <marker id="arrowOrange" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#d97706" />
          </marker>
          <marker id="arrowNDEAxial" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#2563eb" />
          </marker>
        </defs>
      </svg>
      <div className="flex gap-4 mt-2">
        <div className="flex items-center gap-1">
          <div className="w-3 h-1 bg-primary rounded" />
          <span className="text-sm font-medium text-muted-foreground">NDE</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1 bg-amber-500 rounded" />
          <span className="text-sm font-medium text-muted-foreground">DE</span>
        </div>
      </div>
    </div>
  );
}

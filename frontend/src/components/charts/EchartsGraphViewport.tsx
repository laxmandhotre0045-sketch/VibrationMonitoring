import React, { useCallback, useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption, EChartsType } from "echarts";
import { useEchartsResize } from "@/hooks/useEchartsResize";
import {
  applyAdaptiveLineWidth,
  readDataZoomRange,
  resetChartZoom,
  setCrosshairEnabled,
} from "@/lib/graph-interactions";

interface EchartsGraphViewportProps {
  option: EChartsOption;
  chartHeight: number;
  isFullscreen: boolean;
  chartRef: React.RefObject<ReactECharts>;
  onChartReady?: (instance: EChartsType) => void;
  onDataZoom?: (range: { start: number; end: number }) => void;
  crosshairEnabled?: boolean;
  adaptiveLineWidth?: boolean;
  baseLineWidth?: number;
}

export function EchartsGraphViewport({
  option,
  chartHeight,
  isFullscreen,
  chartRef,
  onChartReady,
  onDataZoom,
  crosshairEnabled = true,
  adaptiveLineWidth: enableAdaptive = true,
  baseLineWidth = 1.5,
}: EchartsGraphViewportProps) {
  const [readyInstance, setReadyInstance] = useState<EChartsType | null>(null);

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    [chartRef]
  );

  useEchartsResize(getInstance, [chartHeight, isFullscreen, option]);

  useEffect(() => {
    if (!readyInstance) return;
    setCrosshairEnabled(readyInstance, crosshairEnabled);
  }, [readyInstance, crosshairEnabled]);

  const handleEvents = {
    datazoom: () => {
      const instance = getInstance();
      if (!instance) return;
      const range = readDataZoomRange(instance);
      if (enableAdaptive) {
        applyAdaptiveLineWidth(instance, baseLineWidth);
      }
      onDataZoom?.(range);
    },
    dblclick: () => {
      const instance = getInstance();
      if (!instance) return;
      resetChartZoom(instance);
      if (enableAdaptive) {
        applyAdaptiveLineWidth(instance, baseLineWidth);
      }
      onDataZoom?.({ start: 0, end: 100 });
    },
    finished: () => {
      const instance = getInstance();
      if (!instance) return;
      if (enableAdaptive) {
        applyAdaptiveLineWidth(instance, baseLineWidth);
      }
    },
  };

  const onChartInit = useCallback(
    (instance: EChartsType) => {
      setReadyInstance(instance);
      onChartReady?.(instance);
    },
    [onChartReady]
  );

  return (
    <ReactECharts
      ref={chartRef}
      option={option}
      notMerge
      lazyUpdate
      style={{ width: "100%", height: chartHeight }}
      opts={{ renderer: "canvas" }}
      onEvents={handleEvents}
      onChartReady={onChartInit}
    />
  );
}

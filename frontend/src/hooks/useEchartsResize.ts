import { useEffect } from "react";
import type { EChartsType } from "echarts";

/** Resize ECharts when the container or viewport changes (e.g. fullscreen). */
export function useEchartsResize(
  getInstance: () => EChartsType | undefined,
  deps: unknown[] = []
) {
  useEffect(() => {
    const resize = () => {
      const instance = getInstance();
      if (instance && !instance.isDisposed()) {
        instance.resize();
      }
    };

    resize();
    requestAnimationFrame(resize);
    const retry = window.setTimeout(resize, 150);
    window.addEventListener("resize", resize);

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => resize())
        : null;

    const container = getInstance()?.getDom()?.parentElement;
    if (observer && container) {
      observer.observe(container);
    }

    return () => {
      window.clearTimeout(retry);
      window.removeEventListener("resize", resize);
      observer?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

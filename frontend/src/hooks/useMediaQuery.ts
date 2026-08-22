import { useEffect, useState } from "react";

/**
 * Subscribes to a CSS media query from JS.
 *
 * Use it when a layout decision has to be made in code rather than in classes —
 * e.g. the Dashboard needs to know how many columns the fleet grid is actually
 * rendering so it can size a sibling panel to match.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

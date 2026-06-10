import React from "react";
import { HeroIntelligenceBg } from "./HeroIntelligenceBg";

interface VibrationIntelligenceBgProps {
  className?: string;
  /**
   * hero = premium header backdrop (PageHero, DigitalTwinHeader)
   * page = deprecated; kept for API compat — renders nothing (content areas stay clean)
   */
  variant?: "hero" | "page";
}

/** @deprecated Prefer HeroIntelligenceBg for new header/hero pages. */
export function VibrationIntelligenceBg({ className, variant = "hero" }: VibrationIntelligenceBgProps) {
  if (variant === "page") {
    return null;
  }

  return <HeroIntelligenceBg className={className} />;
}

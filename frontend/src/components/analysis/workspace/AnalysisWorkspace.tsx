import React from "react";
import type { AnalysisTabId } from "@/types/analysis-tabs";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisTabNav } from "./AnalysisTabNav";
import { analysisCardPad } from "@/components/analysis/analysis-layout";

interface AnalysisWorkspaceProps {
  activeTab: AnalysisTabId;
  onTabChange: (tab: AnalysisTabId) => void;
  children: React.ReactNode;
}

export function AnalysisWorkspace({
  activeTab,
  onTabChange,
  children,
}: AnalysisWorkspaceProps) {
  return (
    <GlassCard className={analysisCardPad} delay={0.14}>
      <AnalysisTabNav activeTab={activeTab} onTabChange={onTabChange} className="mb-5" />
      <div role="tabpanel" aria-label={activeTab}>
        {children}
      </div>
    </GlassCard>
  );
}

import React from "react";
import { Check } from "lucide-react";
import { FORM_STEPS } from "@/lib/form-intelligence";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

interface FormStepperProps {
  activeStep: number;
  completedSteps: Set<number>;
  onStepClick: (step: number) => void;
}

export function FormStepper({ activeStep, completedSteps, onStepClick }: FormStepperProps) {
  const maxReachableStep = Math.max(
    activeStep,
    ...Array.from(completedSteps),
    activeStep + 1
  );

  return (
    <div className={cn("content-card card-pad", cardHover.soft)}>
      <div className="flex items-center gap-4 mb-g4 sm:mb-g5">
        <span className="text-base font-medium text-muted-foreground shrink-0">
          Step <span className="font-bold text-[#FF6B00]">{activeStep}</span> of {FORM_STEPS.length}
        </span>
        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${(activeStep / FORM_STEPS.length) * 100}%`,
              background: "linear-gradient(90deg, #FF6B00 0%, #E55F00 100%)",
            }}
          />
        </div>
      </div>

      <div className="overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
        <div className="flex items-start justify-between gap-1 min-w-[540px]">
          {FORM_STEPS.map((step, index) => {
            const isActive = activeStep === step.id;
            const isCompleted = completedSteps.has(step.id);
            const isUpcoming = step.id === activeStep + 1;
            const isAccessible = step.id <= maxReachableStep;

            return (
              <React.Fragment key={step.id}>
                {index > 0 && (
                  <div
                    className={cn(
                      "flex-1 h-0.5 mt-4 min-w-[12px] rounded-full transition-colors",
                      step.id <= activeStep || isCompleted
                        ? "bg-[#FF6B00]/40"
                        : isUpcoming
                          ? "bg-[#FF6B00]/20"
                          : "bg-border"
                    )}
                    aria-hidden
                  />
                )}
                <button
                  type="button"
                  disabled={!isAccessible}
                  onClick={() => isAccessible && onStepClick(step.id)}
                  className={cn(
                    "flex flex-col items-center gap-2 min-w-[80px] max-w-[110px] transition-all duration-200",
                    !isAccessible && "opacity-55 cursor-not-allowed",
                    isAccessible && !isActive && "hover:opacity-90"
                  )}
                >
                  <div
                    className={cn(
                      "w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all duration-200",
                      isActive &&
                        "border-[#FF6B00] bg-[#FF6B00] text-white shadow-cta",
                      !isActive &&
                        isCompleted &&
                        "border-[#FF6B00] bg-[#FF6B00]/10 text-[#FF6B00]",
                      !isActive &&
                        !isCompleted &&
                        isUpcoming &&
                        "border-[#FF6B00] bg-white text-[#FF6B00] shadow-sm",
                      !isActive &&
                        !isCompleted &&
                        !isUpcoming &&
                        "border-border bg-surface text-muted-foreground"
                    )}
                  >
                    {isCompleted && !isActive ? (
                      <Check size={15} strokeWidth={2.5} />
                    ) : (
                      step.id
                    )}
                  </div>
                  <span
                    className={cn(
                      "text-sm font-semibold text-center leading-tight",
                      isActive && "text-[#FF6B00]",
                      isCompleted && !isActive && "text-[#FF6B00]/80",
                      isUpcoming && !isActive && "text-[#FF6B00]/70",
                      !isActive && !isCompleted && !isUpcoming && "text-muted-foreground"
                    )}
                  >
                    {step.shortLabel}
                  </span>
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}

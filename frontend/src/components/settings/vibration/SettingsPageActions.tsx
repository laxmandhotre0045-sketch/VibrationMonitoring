import React from "react";
import { RotateCcw, Save, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface SettingsPageActionsProps {
  isDirty: boolean;
  onSave: () => void;
  onReset: () => void;
  onCancel: () => void;
  className?: string;
}

export function SettingsPageActions({
  isDirty,
  onSave,
  onReset,
  onCancel,
  className,
}: SettingsPageActionsProps) {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-20 -mx-1 mt-g2 rounded-xl border border-border bg-white/95 px-g4 py-g3 backdrop-blur-sm",
        "shadow-[0_-4px_24px_rgba(21,54,109,0.08)]",
        className
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          {isDirty
            ? "You have unsaved changes. Save to apply configuration to this device."
            : "All changes are saved."}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="primary"
            size="md"
            icon={<Save size={16} />}
            disabled={!isDirty}
            onClick={onSave}
          >
            Save Changes
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="md"
            icon={<RotateCcw size={16} />}
            disabled={!isDirty}
            onClick={onReset}
          >
            Reset
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="md"
            icon={<X size={16} />}
            disabled={!isDirty}
            onClick={onCancel}
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

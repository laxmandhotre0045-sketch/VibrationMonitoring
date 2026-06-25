import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

interface SaveBaselineModalProps {
  open: boolean;
  defaultName?: string;
  isSaving?: boolean;
  onClose: () => void;
  onSave: (payload: { name: string; description: string; setAsPrimary: boolean }) => void;
}

export function SaveBaselineModal({
  open,
  defaultName = "",
  isSaving = false,
  onClose,
  onSave,
}: SaveBaselineModalProps) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");
  const [setAsPrimary, setSetAsPrimary] = useState(true);

  useEffect(() => {
    if (open) {
      setName(defaultName);
      setDescription("");
      setSetAsPrimary(true);
    }
  }, [open, defaultName]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-baseline-title"
    >
      <div className="w-full max-w-md rounded-xl border border-border bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h3 id="save-baseline-title" className="text-lg font-bold text-brand">
              Save as baseline
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              Adds a new baseline record.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-surface"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <FormField label="Baseline name">
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Healthy run – June 2026"
            />
          </FormField>
          <FormField label="Description (optional)">
            <TextInput
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Commissioning snapshot, normal load"
            />
          </FormField>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={setAsPrimary}
              onChange={(e) => setSetAsPrimary(e.target.checked)}
              className="rounded border-border"
            />
            Set as primary baseline for this sensor
          </label>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="secondary" onClick={onClose} disabled={isSaving}>
            Cancel
          </Button>
          <Button
            onClick={() => onSave({ name: name.trim(), description: description.trim(), setAsPrimary })}
            disabled={!name.trim() || isSaving}
            className={cn(isSaving && "opacity-70")}
          >
            {isSaving ? "Saving…" : "Save baseline"}
          </Button>
        </div>
      </div>
    </div>
  );
}

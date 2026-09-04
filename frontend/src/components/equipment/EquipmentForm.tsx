import React, { useState } from "react";
import { useForm, FormProvider, useFormContext, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { equipmentSchema, EquipmentFormData } from "@/types/equipment";
import { createEquipment, updateEquipment, uploadEquipmentImage } from "@/api/equipment";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import { DigitalTwinHeader } from "./DigitalTwinHeader";
import { FormStepper } from "./FormStepper";
import { BasicDetailsTab } from "./tabs/BasicDetailsTab";
import { MechanicalDetailsTab } from "./tabs/MechanicalDetailsTab";
import { RotatingComponentsTab } from "./tabs/RotatingComponentsTab";
import { OperatingProcessTab } from "./tabs/OperatingProcessTab";
import { SensorsOrientationTab } from "./tabs/SensorsOrientationTab";
import { ReviewSaveTab } from "./tabs/ReviewSaveTab";
import { EquipmentPageShell } from "./EquipmentPageShell";
import { FORM_STEPS, stepFieldNames } from "@/lib/form-intelligence";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

interface EquipmentFormProps {
  initialData?: EquipmentFormData & { id?: string; created_at?: string; updated_at?: string };
  editId?: string;
}

function FormBreadcrumb({ editId }: { editId?: string }) {
  return (
    <nav className="flex items-center gap-2 text-base font-medium text-muted-foreground">
      <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
      <ChevronRight size={14} />
      <Link to="/equipment" className="hover:text-foreground transition-colors">Equipment Master</Link>
      <ChevronRight size={14} />
      <span className="text-foreground font-semibold">{editId ? "Edit" : "New"}</span>
    </nav>
  );
}

interface FormBodyProps {
  activeTab: number;
  completedTabs: Set<number>;
  setActiveTab: (tab: number) => void;
  editId?: string;
  pendingImage: File | null;
  setPendingImage: (f: File | null) => void;
  saving: boolean;
  onNext: () => void;
  onBack: () => void;
  onSubmit: (data: EquipmentFormData) => Promise<void>;
  onInvalid: (errors: FieldErrors<EquipmentFormData>) => void;
}

function FormBody({
  activeTab,
  completedTabs,
  setActiveTab,
  editId,
  setPendingImage,
  saving,
  onNext,
  onBack,
  onSubmit,
  onInvalid,
}: FormBodyProps) {
  const { watch, handleSubmit } = useFormContext<EquipmentFormData>();
  const data = watch();

  return (
    <EquipmentPageShell>
      <div className="space-y-g5">
        <FormBreadcrumb editId={editId} />
        <DigitalTwinHeader data={data} isEdit={!!editId} />

        {/* Full-bleed: the form is the page. The asset-preview aside that used
            to sit beside it only restated fields already on screen, and it cost
            the form roughly a third of its width on every desktop breakpoint. */}
        <div className="w-full min-w-0 space-y-g5">
          <FormStepper
            activeStep={activeTab}
            completedSteps={completedTabs}
            onStepClick={setActiveTab}
          />

          <form onSubmit={handleSubmit(onSubmit, onInvalid)} className="space-y-g5">
            {/* Keep all tabs mounted so uncontrolled inputs never lose their values */}
            <div style={{ display: activeTab === 1 ? undefined : "none" }}><BasicDetailsTab onImageSelect={setPendingImage} /></div>
            <div style={{ display: activeTab === 2 ? undefined : "none" }}><MechanicalDetailsTab /></div>
            <div style={{ display: activeTab === 3 ? undefined : "none" }}><RotatingComponentsTab /></div>
            <div style={{ display: activeTab === 4 ? undefined : "none" }}><OperatingProcessTab /></div>
            <div style={{ display: activeTab === 5 ? undefined : "none" }}><SensorsOrientationTab /></div>
            <div style={{ display: activeTab === 6 ? undefined : "none" }}><ReviewSaveTab /></div>

            <div className={cn("content-card", cardHover.soft)}>
              <div className="form-actions-bar">
                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  className="w-full sm:w-auto min-h-[44px]"
                  onClick={onBack}
                  disabled={activeTab === 1}
                >
                  ← Back
                </Button>
                {activeTab < 6 ? (
                  <Button
                    type="button"
                    size="lg"
                    className="w-full sm:w-auto min-h-[44px]"
                    onClick={onNext}
                    icon={<ChevronRight size={16} />}
                  >
                    Continue
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="lg"
                    className="w-full sm:w-auto min-h-[44px]"
                    disabled={saving}
                  >
                    {saving ? "Saving..." : "Save & Finish"}
                  </Button>
                )}
              </div>
            </div>
          </form>
        </div>
      </div>
    </EquipmentPageShell>
  );
}

export function EquipmentForm({ initialData, editId }: EquipmentFormProps) {
  const [activeTab, setActiveTab] = useState(1);
  const [completedTabs, setCompletedTabs] = useState<Set<number>>(new Set());
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const methods = useForm<EquipmentFormData>({
    resolver: zodResolver(equipmentSchema),
    defaultValues: initialData || {
      plant_name: "", area: "", line: "",
      machine_name: "", machine_id: null, machine_type: "", machine_criticality: "",
      sensors: [],
      asset_status: "Active",
      machine_train_configured: false,
      bearing_database_mapped: false,
      operating_mode_configured: false,
      operating_environment: [],
    },
    mode: "onChange",
  });

  const goToTab = (tabId: number) => {
    if (tabId > activeTab) setCompletedTabs((prev) => new Set([...prev, activeTab]));
    setActiveTab(tabId);
  };

  /**
   * A rejected save used to do nothing at all: react-hook-form swallows the
   * submit when the resolver reports an error, and with the failing field
   * usually parked on a step the user is not looking at, the Save button simply
   * appeared dead. Name the field instead, and jump to the step holding it.
   */
  const onInvalid = (errors: FieldErrors<EquipmentFormData>) => {
    const [field] = Object.keys(errors);
    if (!field) return;
    const step = FORM_STEPS.find((s) => stepFieldNames(s.id).includes(field));
    if (step) setActiveTab(step.id);
    const message =
      (errors as Record<string, { message?: string }>)[field]?.message ??
      "Please check the highlighted field.";
    showToast(`${field.replace(/_/g, " ")}: ${message}`, "error");
  };

  const onSubmit = async (data: EquipmentFormData) => {
    setSaving(true);
    try {
      let equipment;
      if (editId) {
        equipment = await updateEquipment(editId, data);
        showToast("Equipment updated successfully!", "success");
      } else {
        equipment = await createEquipment(data);
        showToast("Equipment saved successfully!", "success");
      }
      if (pendingImage && equipment.id) {
        await uploadEquipmentImage(equipment.id, pendingImage);
      }
      setCompletedTabs(new Set([1, 2, 3, 4, 5, 6]));
      setTimeout(() => navigate("/equipment"), 1200);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Failed to save equipment. Please try again.";
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormProvider {...methods}>
      <FormBody
        activeTab={activeTab}
        completedTabs={completedTabs}
        setActiveTab={goToTab}
        editId={editId}
        pendingImage={pendingImage}
        setPendingImage={setPendingImage}
        saving={saving}
        onNext={() => goToTab(activeTab + 1)}
        onBack={() => setActiveTab((t) => Math.max(1, t - 1))}
        onSubmit={onSubmit}
        onInvalid={onInvalid}
      />
    </FormProvider>
  );
}

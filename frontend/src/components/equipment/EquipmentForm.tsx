import React, { useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import {
  MapPin, Cpu, Settings, RotateCw, Activity, Wrench, Radio, Brain, CheckCircle, ChevronRight,
} from "lucide-react";
import { equipmentSchema, EquipmentFormData } from "@/types/equipment";
import { createEquipment, updateEquipment, uploadEquipmentImage } from "@/api/equipment";
import { useToast } from "@/components/ui/Toast";
import { BasicDetailsTab } from "./tabs/BasicDetailsTab";
import { MechanicalDetailsTab } from "./tabs/MechanicalDetailsTab";
import { RotatingComponentsTab } from "./tabs/RotatingComponentsTab";
import { OperatingProcessTab } from "./tabs/OperatingProcessTab";
import { SensorsOrientationTab } from "./tabs/SensorsOrientationTab";
import { ReviewSaveTab } from "./tabs/ReviewSaveTab";
import { cn } from "@/lib/utils";

const TABS = [
  { id: 1, label: "Basic Details", icon: <MapPin size={14} /> },
  { id: 2, label: "Mechanical Details", icon: <Settings size={14} /> },
  { id: 3, label: "Rotating Components", icon: <RotateCw size={14} /> },
  { id: 4, label: "Operating & Process", icon: <Activity size={14} /> },
  { id: 5, label: "Sensors & Orientation", icon: <Radio size={14} /> },
  { id: 6, label: "Review & Save", icon: <Brain size={14} /> },
];

const TAB_FIELDS: Record<number, (keyof EquipmentFormData)[]> = {
  1: ["plant_name", "area", "line", "machine_name", "machine_id", "machine_type", "machine_criticality"],
  2: [],
  3: [],
  4: [],
  5: [],
  6: [],
};

interface EquipmentFormProps {
  initialData?: EquipmentFormData & { id?: string };
  editId?: string;
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
      machine_name: "", machine_id: "", machine_type: "", machine_criticality: "",
      sensors: [],
      asset_status: "Active",
      machine_train_configured: false,
      bearing_database_mapped: false,
      operating_mode_configured: false,
      operating_environment: [],
    },
    mode: "onChange",
  });

  const { handleSubmit, formState: { errors } } = methods;

  const goToTab = (tabId: number) => {
    if (tabId > activeTab) {
      setCompletedTabs((prev) => new Set([...prev, activeTab]));
    }
    setActiveTab(tabId);
  };

  const onNext = () => goToTab(activeTab + 1);
  const onBack = () => setActiveTab((t) => Math.max(1, t - 1));
  const tabHasError = (_tabId: number) => false;

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
      setTimeout(() => navigate("/"), 1200);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Failed to save equipment. Please try again.";
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  };


  return (
    <FormProvider {...methods}>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-30 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <Cpu size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-gray-900">Equipment Master Data</h1>
              <p className="text-xs text-gray-500">AI Vibration Intelligence Platform</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            Cancel
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="bg-white border-b border-gray-200 px-6 sticky top-[65px] z-20 shadow-sm">
          <div className="flex items-center gap-1 overflow-x-auto py-2 scrollbar-hide">
            {TABS.map((tab, idx) => {
              const isActive = activeTab === tab.id;
              const isCompleted = completedTabs.has(tab.id);
              const isAccessible = tab.id <= activeTab || isCompleted;
              const hasErr = tabHasError(tab.id);
              return (
                <React.Fragment key={tab.id}>
                  <button
                    type="button"
                    onClick={() => isAccessible && setActiveTab(tab.id)}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
                      isActive
                        ? "bg-blue-600 text-white shadow-sm"
                        : isCompleted && !hasErr
                        ? "bg-blue-50 text-blue-700 border border-blue-200"
                        : hasErr
                        ? "bg-red-50 text-red-600 border border-red-200"
                        : "text-gray-500 hover:bg-gray-100 border border-transparent",
                      !isAccessible && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    <span className={cn(
                      "w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold",
                      isActive ? "bg-blue-500" : isCompleted ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-600"
                    )}>
                      {isCompleted && !isActive ? <CheckCircle size={12} /> : tab.id}
                    </span>
                    {tab.icon}
                    {tab.label}
                  </button>
                  {idx < TABS.length - 1 && (
                    <ChevronRight size={14} className="text-gray-300 shrink-0" />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Form Content */}
        <form onSubmit={handleSubmit(onSubmit)} className="max-w-7xl mx-auto px-6 py-6">
          {activeTab === 1 && <BasicDetailsTab onImageSelect={setPendingImage} />}
          {activeTab === 2 && <MechanicalDetailsTab />}
          {activeTab === 3 && <RotatingComponentsTab />}
          {activeTab === 4 && <OperatingProcessTab />}
          {activeTab === 5 && <SensorsOrientationTab />}
          {activeTab === 6 && <ReviewSaveTab />}

          {/* Footer Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-gray-200">
            <button
              type="button"
              onClick={onBack}
              disabled={activeTab === 1}
              className="px-5 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              ← Back
            </button>

            <div className="flex items-center gap-2">
              {TABS.map((tab) => (
                <div
                  key={tab.id}
                  className={cn(
                    "w-2 h-2 rounded-full transition-all",
                    activeTab === tab.id ? "bg-blue-600 w-6" : completedTabs.has(tab.id) ? "bg-blue-300" : "bg-gray-200"
                  )}
                />
              ))}
            </div>

            {activeTab < 6 ? (
              <button
                type="button"
                onClick={onNext}
                className="px-5 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-all flex items-center gap-2"
              >
                Next <ChevronRight size={16} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={saving}
                className="px-6 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-all flex items-center gap-2"
              >
                {saving ? (
                  <>
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                    Saving...
                  </>
                ) : (
                  "Save & Finish"
                )}
              </button>
            )}
          </div>
        </form>
      </div>
    </FormProvider>
  );
}

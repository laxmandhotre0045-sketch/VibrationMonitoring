import React from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getEquipment } from "@/api/equipment";
import { EquipmentForm } from "@/components/equipment/EquipmentForm";
import type { EquipmentFormData } from "@/types/equipment";

export function NewEquipmentPage() {
  return <EquipmentForm />;
}

export function EditEquipmentPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["equipment", id],
    queryFn: () => getEquipment(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <svg className="animate-spin h-8 w-8 text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          <p className="text-sm">Loading equipment data...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-red-500 text-sm">Failed to load equipment. Please try again.</p>
      </div>
    );
  }

  const initialData: EquipmentFormData & { id: string } = {
    ...data,
    sensors: data.sensors || [],
    operating_environment: data.operating_environment || [],
    installation_date: data.installation_date ? String(data.installation_date).split("T")[0] : undefined,
    last_maintenance_date: data.last_maintenance_date ? String(data.last_maintenance_date).split("T")[0] : undefined,
  };

  return <EquipmentForm initialData={initialData} editId={id} />;
}

import React from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { getEquipment } from "@/api/equipment";
import { EquipmentForm } from "@/components/equipment/EquipmentForm";
import type { EquipmentFormData } from "@/types/equipment";

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-32 gap-4">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        className="w-10 h-10 rounded-lg border-2 border-brand border-t-transparent"
      />
      <p className="text-helper">Loading equipment data...</p>
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex flex-col items-center justify-center py-32 gap-3">
      <p className="text-destructive font-bold">Failed to load equipment.</p>
      <p className="text-helper">Please try again.</p>
    </div>
  );
}

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

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState />;

  const initialData: EquipmentFormData & { id: string } = {
    ...data,
    sensors: data.sensors || [],
    operating_environment: data.operating_environment || [],
    installation_date: data.installation_date
      ? String(data.installation_date).split("T")[0]
      : undefined,
    last_maintenance_date: data.last_maintenance_date
      ? String(data.last_maintenance_date).split("T")[0]
      : undefined,
  };

  return <EquipmentForm initialData={initialData} editId={id} />;
}

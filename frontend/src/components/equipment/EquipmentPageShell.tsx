import React from "react";

interface EquipmentPageShellProps {
  children: React.ReactNode;
}

/** Equipment Master pages — content shell (no decorative page background). */
export function EquipmentPageShell({ children }: EquipmentPageShellProps) {
  return <div className="relative">{children}</div>;
}

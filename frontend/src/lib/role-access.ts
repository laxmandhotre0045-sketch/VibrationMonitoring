export const ALL_ROLES = [
  "super_admin",
  "plant_admin",
  "engineer",
  "operator",
  "viewer",
] as const;

export const WRITE_ROLES = ["super_admin", "plant_admin", "engineer"] as const;

export const ADMIN_ROLES = ["super_admin", "plant_admin"] as const;

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "SUPER ADMIN",
  plant_admin: "PLANT ADMIN",
  engineer: "ENGINEER",
  operator: "OPERATOR",
  viewer: "VIEWER",
};

const ROLE_PRIORITY = [
  "super_admin",
  "plant_admin",
  "engineer",
  "operator",
  "viewer",
];

export function primaryRole(roles: string[]): string | null {
  return ROLE_PRIORITY.find((r) => roles.includes(r)) ?? roles[0] ?? null;
}

export function roleLabel(role: string | null): string {
  if (!role) return "USER";
  return ROLE_LABELS[role] ?? role.replace(/_/g, " ").toUpperCase();
}

export function hasAnyRole(userRoles: string[], required: string[]): boolean {
  if (required.length === 0) return true;
  return required.some((r) => userRoles.includes(r));
}

export const ALL_ROLES = ["super_admin", "admin", "user"] as const;

export const WRITE_ROLES = ["super_admin", "admin"] as const;

export const ADMIN_ROLES = ["super_admin", "admin"] as const;

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "SUPER ADMIN",
  admin: "ADMIN",
  user: "USER",
};

const ROLE_PRIORITY = ["super_admin", "admin", "user"];

export function primaryRole(roles: readonly string[]): string | null {
  return ROLE_PRIORITY.find((r) => roles.includes(r)) ?? roles[0] ?? null;
}

export function roleLabel(role: string | null): string {
  if (!role) return "USER";
  return ROLE_LABELS[role] ?? role.replace(/_/g, " ").toUpperCase();
}

export function hasAnyRole(userRoles: string[], required: readonly string[]): boolean {
  if (required.length === 0) return true;
  return required.some((r) => userRoles.includes(r));
}

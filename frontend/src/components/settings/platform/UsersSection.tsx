import React, { useMemo, useState } from "react";
import { KeyRound, Pencil, Plus, Search, Trash2, Users } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField, SelectInput, TextInput } from "@/components/ui/FormField";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ConfirmDialog, PlatformDialog } from "./PlatformDialog";
import {
  EmptyRow,
  ErrorNote,
  IconAction,
  LoadingRow,
  SecretReveal,
  StatusPill,
  formatDateTime,
  platformTable,
  platformTableWrapper,
  platformTd,
  platformTh,
} from "./platform-ui";
import {
  useCreateUser,
  useDeleteUser,
  useResetPassword,
  useRoles,
  useUpdateUser,
  useUsers,
} from "@/hooks/usePlatformSettings";
import { useAuth } from "@/contexts/AuthContext";
import { ALL_ROLES, roleLabel } from "@/lib/role-access";
import { apiErrorMessage } from "@/lib/api-error";
import type { PlatformUser } from "@/types/platform";

const MIN_PASSWORD_LENGTH = 8;

/**
 * Admins should not be inventing passwords by hand, and the value only has to
 * survive until the user's forced change at first sign-in.
 */
function generatePassword(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const bytes = new Uint32Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (n) => alphabet[n % alphabet.length]).join("");
}

function roleTone(role: string) {
  if (role === "super_admin") return "warning" as const;
  if (role === "admin") return "healthy" as const;
  return "muted" as const;
}

export function UsersSection() {
  const { user: currentUser, hasRole } = useAuth();
  const isSuperAdmin = hasRole("super_admin");

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const filters = useMemo(
    () => ({
      search: search.trim() || undefined,
      role: roleFilter || undefined,
      is_active: statusFilter === "" ? undefined : statusFilter === "active",
    }),
    [search, roleFilter, statusFilter]
  );

  const { data: users, isLoading, error } = useUsers(filters);
  const { data: roles } = useRoles();

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<PlatformUser | null>(null);
  const [resetting, setResetting] = useState<PlatformUser | null>(null);
  const [deleting, setDeleting] = useState<PlatformUser | null>(null);

  const deleteUser = useDeleteUser();

  const roleOptions = useMemo(() => {
    const names = roles?.length ? roles.map((r) => r.name) : [...ALL_ROLES];
    // Only a super admin may create or promote to super_admin, so offering the
    // option to anyone else would just produce a 403 on submit.
    return isSuperAdmin ? names : names.filter((name) => name !== "super_admin");
  }, [roles, isSuperAdmin]);

  return (
    <div className="space-y-4">
      <SettingsSectionCard
        title="Users & access"
        description="Who can sign in, and what each of them is allowed to change."
        icon={<Users size={18} />}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center flex-1 min-w-0">
            <div className="relative flex-1 min-w-0 sm:max-w-xs">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
              />
              <TextInput
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search name or email"
                className="pl-9 py-2 text-sm"
              />
            </div>
            <SelectInput
              options={roleOptions}
              placeholder="All roles"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="py-2 text-sm sm:w-40"
            />
            <SelectInput
              options={["active", "inactive"]}
              placeholder="All statuses"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="py-2 text-sm sm:w-40"
            />
          </div>
          <Button size="sm" icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            Add user
          </Button>
        </div>

        {error && <ErrorNote message={apiErrorMessage(error, "Failed to load users")} />}

        <div className={platformTableWrapper}>
          <table className={platformTable}>
            <thead>
              <tr>
                <th className={platformTh}>User</th>
                <th className={platformTh}>Role</th>
                <th className={platformTh}>Status</th>
                <th className={platformTh}>Last sign-in</th>
                <th className={platformTh}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <LoadingRow colSpan={5} />}
              {!isLoading && !users?.length && (
                <EmptyRow colSpan={5} message="No users match these filters." />
              )}
              {users?.map((user) => {
                const isSelf = user.id === currentUser?.id;
                // The server refuses these for the same reasons; disabling them
                // here means the admin never has to discover that by failing.
                const locked = user.role === "super_admin" && !isSuperAdmin;

                return (
                  <tr key={user.id} className="hover:bg-warm/60 transition-colors">
                    <td className={platformTd}>
                      <div className="font-semibold text-foreground">
                        {user.full_name}
                        {isSelf && (
                          <span className="ml-2 text-xs font-medium text-muted-foreground">
                            (you)
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">{user.email}</div>
                    </td>
                    <td className={platformTd}>
                      <StatusPill tone={roleTone(user.role)}>{roleLabel(user.role)}</StatusPill>
                    </td>
                    <td className={platformTd}>
                      <div className="flex flex-wrap gap-1.5">
                        <StatusPill tone={user.is_active ? "healthy" : "muted"}>
                          {user.is_active ? "Active" : "Inactive"}
                        </StatusPill>
                        {user.must_change_password && (
                          <StatusPill tone="warning">Password reset pending</StatusPill>
                        )}
                      </div>
                    </td>
                    <td className={`${platformTd} text-muted-foreground whitespace-nowrap`}>
                      {formatDateTime(user.last_login_at)}
                    </td>
                    <td className={platformTd}>
                      <div className="flex items-center gap-1">
                        <IconAction
                          label="Edit user"
                          disabled={locked}
                          onClick={() => setEditing(user)}
                        >
                          <Pencil size={15} />
                        </IconAction>
                        <IconAction
                          label="Reset password"
                          disabled={locked}
                          onClick={() => setResetting(user)}
                        >
                          <KeyRound size={15} />
                        </IconAction>
                        <IconAction
                          label={isSelf ? "You cannot delete your own account" : "Delete user"}
                          tone="danger"
                          disabled={locked || isSelf}
                          onClick={() => setDeleting(user)}
                        >
                          <Trash2 size={15} />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SettingsSectionCard>

      <CreateUserDialog
        open={createOpen}
        roleOptions={roleOptions}
        onClose={() => setCreateOpen(false)}
      />
      <EditUserDialog
        user={editing}
        roleOptions={roleOptions}
        isSelf={editing?.id === currentUser?.id}
        onClose={() => setEditing(null)}
      />
      <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete user"
        confirmLabel="Delete user"
        busy={deleteUser.isPending}
        message={
          <>
            <strong>{deleting?.full_name}</strong> ({deleting?.email}) will lose access
            immediately and any active sessions will be revoked. This cannot be undone.
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          deleteUser.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
      />
    </div>
  );
}

// ── Dialogs ─────────────────────────────────────────────────────────────────

function CreateUserDialog({
  open,
  roleOptions,
  onClose,
}: {
  open: boolean;
  roleOptions: string[];
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("user");
  const [password, setPassword] = useState(generatePassword);
  const [createdFor, setCreatedFor] = useState<string | null>(null);

  const createUser = useCreateUser(() => setCreatedFor(email));

  function reset() {
    setEmail("");
    setFullName("");
    setRole("user");
    setPassword(generatePassword());
    setCreatedFor(null);
  }

  function close() {
    reset();
    onClose();
  }

  const canSubmit =
    email.trim().length > 3 &&
    fullName.trim().length > 0 &&
    password.length >= MIN_PASSWORD_LENGTH;

  // After a successful create the dialog switches to showing the temporary
  // password, because that is the only moment the admin can hand it over.
  if (createdFor) {
    return (
      <PlatformDialog
        open={open}
        title="User created"
        description={`Share these credentials with ${createdFor} over a trusted channel.`}
        onClose={close}
        footer={
          <Button size="sm" onClick={close}>
            Done
          </Button>
        }
      >
        <SecretReveal
          label="Temporary password"
          secret={password}
          warning="The user must change this at their first sign-in. It is not stored in readable form, so copy it now — it cannot be shown again."
        />
      </PlatformDialog>
    );
  }

  return (
    <PlatformDialog
      open={open}
      title="Add user"
      description="The account starts with a temporary password that must be changed at first sign-in."
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!canSubmit || createUser.isPending}
            onClick={() =>
              createUser.mutate({
                email: email.trim(),
                full_name: fullName.trim(),
                password,
                role,
                is_active: true,
                must_change_password: true,
              })
            }
          >
            {createUser.isPending ? "Creating…" : "Create user"}
          </Button>
        </>
      }
    >
      <FormField label="Full name" required compact>
        <TextInput
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Anita Deshmukh"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField label="Email" required compact>
        <TextInput
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="anita@plant.example"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField label="Role" required compact>
        <SelectInput
          options={roleOptions}
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField
        label="Temporary password"
        compact
        hint="Generated for you. Regenerate if you would rather not reuse what is on screen."
      >
        <div className="flex items-stretch gap-2">
          <TextInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="py-2.5 text-sm font-mono"
          />
          <Button variant="secondary" size="sm" onClick={() => setPassword(generatePassword())}>
            Regenerate
          </Button>
        </div>
      </FormField>
    </PlatformDialog>
  );
}

function EditUserDialog({
  user,
  roleOptions,
  isSelf,
  onClose,
}: {
  user: PlatformUser | null;
  roleOptions: string[];
  isSelf?: boolean;
  onClose: () => void;
}) {
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("user");
  const [isActive, setIsActive] = useState(true);

  React.useEffect(() => {
    if (!user) return;
    setFullName(user.full_name);
    setRole(user.role);
    setIsActive(user.is_active);
  }, [user]);

  const updateUser = useUpdateUser(onClose);

  return (
    <PlatformDialog
      open={Boolean(user)}
      title="Edit user"
      description={user?.email}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!fullName.trim() || updateUser.isPending}
            onClick={() => {
              if (!user) return;
              updateUser.mutate({
                userId: user.id,
                payload: { full_name: fullName.trim(), role, is_active: isActive },
              });
            }}
          >
            {updateUser.isPending ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <FormField label="Full name" required compact>
        <TextInput
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField
        label="Role"
        compact
        hint={isSelf ? "You cannot change your own role — ask another admin." : undefined}
      >
        <SelectInput
          options={roleOptions}
          value={role}
          disabled={isSelf}
          onChange={(e) => setRole(e.target.value)}
          className="py-2.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
        />
      </FormField>
      <label
        className={`flex items-center gap-2.5 text-sm text-foreground ${
          isSelf ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
        }`}
      >
        <input
          type="checkbox"
          checked={isActive}
          disabled={isSelf}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-[#FF6B00]"
        />
        <span>
          Account is active
          <span className="block text-xs text-muted-foreground">
            {isSelf
              ? "You cannot deactivate your own account."
              : "Deactivating signs the user out of every session."}
          </span>
        </span>
      </label>
    </PlatformDialog>
  );
}

function ResetPasswordDialog({
  user,
  onClose,
}: {
  user: PlatformUser | null;
  onClose: () => void;
}) {
  const [password, setPassword] = useState(generatePassword);
  const [done, setDone] = useState(false);

  React.useEffect(() => {
    if (user) {
      setPassword(generatePassword());
      setDone(false);
    }
  }, [user]);

  const resetPassword = useResetPassword(() => setDone(true));

  function close() {
    setDone(false);
    onClose();
  }

  if (done) {
    return (
      <PlatformDialog
        open={Boolean(user)}
        title="Password reset"
        description={`Share the new password with ${user?.email} over a trusted channel.`}
        onClose={close}
        footer={
          <Button size="sm" onClick={close}>
            Done
          </Button>
        }
      >
        <SecretReveal
          label="New temporary password"
          secret={password}
          warning="Existing sessions have been revoked and the user must change this at their next sign-in. Copy it now — it cannot be shown again."
        />
      </PlatformDialog>
    );
  }

  return (
    <PlatformDialog
      open={Boolean(user)}
      title="Reset password"
      description={user?.full_name}
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={password.length < MIN_PASSWORD_LENGTH || resetPassword.isPending}
            onClick={() => {
              if (!user) return;
              resetPassword.mutate({ userId: user.id, newPassword: password });
            }}
          >
            {resetPassword.isPending ? "Resetting…" : "Reset password"}
          </Button>
        </>
      }
    >
      <FormField
        label="New temporary password"
        compact
        hint="The user will be forced to change this at their next sign-in, and all their current sessions will be revoked."
      >
        <div className="flex items-stretch gap-2">
          <TextInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="py-2.5 text-sm font-mono"
          />
          <Button variant="secondary" size="sm" onClick={() => setPassword(generatePassword())}>
            Regenerate
          </Button>
        </div>
      </FormField>
    </PlatformDialog>
  );
}

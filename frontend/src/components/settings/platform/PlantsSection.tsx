import React, { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Factory,
  Layers,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ConfirmDialog, PlatformDialog } from "./PlatformDialog";
import { ErrorNote, IconAction, StatusPill } from "./platform-ui";
import {
  useCreateArea,
  useCreateLine,
  useCreatePlant,
  useDeleteArea,
  useDeleteLine,
  useDeletePlant,
  usePlantDetail,
  usePlants,
  useUpdateArea,
  useUpdateLine,
  useUpdatePlant,
} from "@/hooks/usePlatformSettings";
import { apiErrorMessage } from "@/lib/api-error";
import { cn } from "@/lib/utils";
import type { Plant, PlantArea, PlantLine } from "@/types/platform";

type NodeKind = "plant" | "area" | "line";

interface NodeEdit {
  kind: NodeKind;
  id: string;
  name: string;
  code?: string | null;
  location?: string | null;
  is_active: boolean;
}

interface NodeDelete {
  kind: NodeKind;
  id: string;
  name: string;
  equipmentCount: number;
}

export function PlantsSection() {
  const { data: plants, isLoading, error } = usePlants();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<NodeEdit | null>(null);
  const [deleting, setDeleting] = useState<NodeDelete | null>(null);
  const [addingAreaTo, setAddingAreaTo] = useState<Plant | null>(null);
  const [addingLineTo, setAddingLineTo] = useState<PlantArea | null>(null);

  return (
    <div className="space-y-g4">
      <SettingsSectionCard
        title="Plants, areas & lines"
        description="The hierarchy every equipment record is filed under. Renaming a plant updates the equipment already assigned to it."
        icon={<Factory size={18} />}
      >
        <div className="flex items-center justify-between gap-g2 mb-g3">
          <p className="text-sm text-muted-foreground">
            {plants?.length ?? 0} plant{plants?.length === 1 ? "" : "s"} configured
          </p>
          <Button size="sm" icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            Add plant
          </Button>
        </div>

        {error && <ErrorNote message={apiErrorMessage(error, "Failed to load plants")} />}

        {isLoading && (
          <div className="flex items-center justify-center gap-g2 py-g6 text-sm text-muted-foreground">
            <Loader2 size={16} className="animate-spin" />
            Loading hierarchy…
          </div>
        )}

        {!isLoading && !plants?.length && (
          <div className="rounded-lg border border-dashed border-border bg-warm px-g4 py-g6 text-center">
            <p className="text-sm font-semibold text-foreground">No plants yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Add a plant to start filing equipment under a hierarchy.
            </p>
          </div>
        )}

        <div className="space-y-2">
          {plants?.map((plant) => (
            <PlantRow
              key={plant.id}
              plant={plant}
              expanded={expandedId === plant.id}
              onToggle={() => setExpandedId(expandedId === plant.id ? null : plant.id)}
              onEdit={() =>
                setEditing({
                  kind: "plant",
                  id: plant.id,
                  name: plant.name,
                  code: plant.code,
                  location: plant.location,
                  is_active: plant.is_active,
                })
              }
              onDelete={() =>
                setDeleting({
                  kind: "plant",
                  id: plant.id,
                  name: plant.name,
                  equipmentCount: plant.equipment_count,
                })
              }
              onAddArea={() => setAddingAreaTo(plant)}
              onEditArea={(area) =>
                setEditing({
                  kind: "area",
                  id: area.id,
                  name: area.name,
                  is_active: area.is_active,
                })
              }
              onDeleteArea={(area) =>
                setDeleting({
                  kind: "area",
                  id: area.id,
                  name: area.name,
                  equipmentCount: area.equipment_count,
                })
              }
              onAddLine={(area) => setAddingLineTo(area)}
              onEditLine={(line) =>
                setEditing({
                  kind: "line",
                  id: line.id,
                  name: line.name,
                  is_active: line.is_active,
                })
              }
              onDeleteLine={(line) =>
                setDeleting({
                  kind: "line",
                  id: line.id,
                  name: line.name,
                  equipmentCount: line.equipment_count,
                })
              }
            />
          ))}
        </div>
      </SettingsSectionCard>

      <CreatePlantDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <AddNodeDialog
        kind="area"
        parentName={addingAreaTo?.name}
        parentId={addingAreaTo?.id ?? null}
        onClose={() => setAddingAreaTo(null)}
      />
      <AddNodeDialog
        kind="line"
        parentName={addingLineTo?.name}
        parentId={addingLineTo?.id ?? null}
        onClose={() => setAddingLineTo(null)}
      />
      <EditNodeDialog node={editing} onClose={() => setEditing(null)} />
      <DeleteNodeDialog node={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}

// ── Tree rows ───────────────────────────────────────────────────────────────

interface PlantRowProps {
  plant: Plant;
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onAddArea: () => void;
  onEditArea: (area: PlantArea) => void;
  onDeleteArea: (area: PlantArea) => void;
  onAddLine: (area: PlantArea) => void;
  onEditLine: (line: PlantLine) => void;
  onDeleteLine: (line: PlantLine) => void;
}

function PlantRow({
  plant,
  expanded,
  onToggle,
  onEdit,
  onDelete,
  onAddArea,
  onEditArea,
  onDeleteArea,
  onAddLine,
  onEditLine,
  onDeleteLine,
}: PlantRowProps) {
  // Areas and lines are only fetched for the plant actually open, so a large
  // estate does not pull its whole tree on every visit to this tab.
  const { data: detail, isLoading } = usePlantDetail(expanded ? plant.id : null);

  return (
    <div className="rounded-lg border border-border bg-white overflow-hidden">
      <div className="flex items-center gap-g2 px-g4 py-g3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <span className="shrink-0 text-muted-foreground">
            {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </span>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/[0.06] text-brand/70">
            <Factory size={17} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-foreground">{plant.name}</span>
              {plant.code && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                  {plant.code}
                </span>
              )}
              {!plant.is_active && <StatusPill tone="muted">Inactive</StatusPill>}
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              {plant.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin size={11} />
                  {plant.location}
                </span>
              )}
              <span>
                {plant.area_count} area{plant.area_count === 1 ? "" : "s"}
              </span>
              <span>
                {plant.equipment_count} equipment record
                {plant.equipment_count === 1 ? "" : "s"}
              </span>
            </span>
          </span>
        </button>

        <div className="flex shrink-0 items-center gap-1">
          <IconAction label="Add area" onClick={onAddArea}>
            <Plus size={15} />
          </IconAction>
          <IconAction label="Edit plant" onClick={onEdit}>
            <Pencil size={15} />
          </IconAction>
          <IconAction label="Delete plant" tone="danger" onClick={onDelete}>
            <Trash2 size={15} />
          </IconAction>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border bg-warm/50 px-g4 py-g3">
          {isLoading && (
            <p className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Loading areas…
            </p>
          )}

          {!isLoading && !detail?.areas.length && (
            <p className="py-2 text-sm text-muted-foreground">
              No areas yet. Use the + button above to add one.
            </p>
          )}

          <div className="space-y-2">
            {detail?.areas.map((area) => (
              <div key={area.id} className="rounded-lg border border-border bg-white">
                <div className="flex items-center gap-2.5 px-3 py-2.5">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#FFA500]/12 text-signal-dark">
                    <Layers size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{area.name}</span>
                      {!area.is_active && <StatusPill tone="muted">Inactive</StatusPill>}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {area.lines.length} line{area.lines.length === 1 ? "" : "s"} ·{" "}
                      {area.equipment_count} equipment
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <IconAction label="Add line" onClick={() => onAddLine(area)}>
                      <Plus size={14} />
                    </IconAction>
                    <IconAction label="Edit area" onClick={() => onEditArea(area)}>
                      <Pencil size={14} />
                    </IconAction>
                    <IconAction
                      label="Delete area"
                      tone="danger"
                      onClick={() => onDeleteArea(area)}
                    >
                      <Trash2 size={14} />
                    </IconAction>
                  </div>
                </div>

                {area.lines.length > 0 && (
                  <ul className="border-t border-border/70 px-3 py-1.5">
                    {area.lines.map((line) => (
                      <li
                        key={line.id}
                        className="flex items-center gap-2 py-1.5 pl-8 text-sm relative"
                      >
                        <span
                          className="absolute left-3 top-0 bottom-0 w-px bg-border"
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1">
                          <span
                            className={cn(
                              "text-foreground",
                              !line.is_active && "text-muted-foreground line-through"
                            )}
                          >
                            {line.name}
                          </span>
                          <span className="ml-2 text-xs text-muted-foreground">
                            {line.equipment_count} equipment
                          </span>
                        </span>
                        <IconAction label="Edit line" onClick={() => onEditLine(line)}>
                          <Pencil size={13} />
                        </IconAction>
                        <IconAction
                          label="Delete line"
                          tone="danger"
                          onClick={() => onDeleteLine(line)}
                        >
                          <Trash2 size={13} />
                        </IconAction>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Dialogs ─────────────────────────────────────────────────────────────────

function CreatePlantDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [location, setLocation] = useState("");

  function close() {
    setName("");
    setCode("");
    setLocation("");
    onClose();
  }

  const createPlant = useCreatePlant(close);

  return (
    <PlatformDialog
      open={open}
      title="Add plant"
      description="Areas and production lines can be added once the plant exists."
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!name.trim() || createPlant.isPending}
            onClick={() =>
              createPlant.mutate({
                name: name.trim(),
                code: code.trim() || null,
                location: location.trim() || null,
                is_active: true,
              })
            }
          >
            {createPlant.isPending ? "Creating…" : "Create plant"}
          </Button>
        </>
      }
    >
      <FormField label="Plant name" required compact>
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Pune Works"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField label="Code" compact>
        <TextInput
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="PUN-01"
          className="py-2.5 text-sm"
        />
      </FormField>
      <FormField label="Location" compact>
        <TextInput
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Chakan, Maharashtra"
          className="py-2.5 text-sm"
        />
      </FormField>
    </PlatformDialog>
  );
}

function AddNodeDialog({
  kind,
  parentId,
  parentName,
  onClose,
}: {
  kind: "area" | "line";
  parentId: string | null;
  parentName?: string;
  onClose: () => void;
}) {
  const [name, setName] = useState("");

  function close() {
    setName("");
    onClose();
  }

  const createArea = useCreateArea(close);
  const createLine = useCreateLine(close);
  const mutation = kind === "area" ? createArea : createLine;

  return (
    <PlatformDialog
      open={Boolean(parentId)}
      title={kind === "area" ? "Add area" : "Add production line"}
      description={parentName ? `Inside ${parentName}` : undefined}
      widthClassName="max-w-md"
      onClose={close}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!name.trim() || mutation.isPending}
            onClick={() => {
              if (!parentId) return;
              if (kind === "area") {
                createArea.mutate({ plantId: parentId, name: name.trim() });
              } else {
                createLine.mutate({ areaId: parentId, name: name.trim() });
              }
            }}
          >
            {mutation.isPending ? "Adding…" : "Add"}
          </Button>
        </>
      }
    >
      <FormField label={kind === "area" ? "Area name" : "Line name"} required compact>
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={kind === "area" ? "Compressor House" : "Line 2"}
          className="py-2.5 text-sm"
        />
      </FormField>
    </PlatformDialog>
  );
}

const NODE_LABELS: Record<NodeKind, string> = {
  plant: "plant",
  area: "area",
  line: "line",
};

function EditNodeDialog({ node, onClose }: { node: NodeEdit | null; onClose: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [location, setLocation] = useState("");
  const [isActive, setIsActive] = useState(true);

  React.useEffect(() => {
    if (!node) return;
    setName(node.name);
    setCode(node.code ?? "");
    setLocation(node.location ?? "");
    setIsActive(node.is_active);
  }, [node]);

  const updatePlant = useUpdatePlant(onClose);
  const updateArea = useUpdateArea(onClose);
  const updateLine = useUpdateLine(onClose);

  const pending = updatePlant.isPending || updateArea.isPending || updateLine.isPending;

  function submit() {
    if (!node) return;
    const trimmed = name.trim();
    if (node.kind === "plant") {
      updatePlant.mutate({
        plantId: node.id,
        payload: {
          name: trimmed,
          code: code.trim() || null,
          location: location.trim() || null,
          is_active: isActive,
        },
      });
    } else if (node.kind === "area") {
      updateArea.mutate({ areaId: node.id, payload: { name: trimmed, is_active: isActive } });
    } else {
      updateLine.mutate({ lineId: node.id, payload: { name: trimmed, is_active: isActive } });
    }
  }

  return (
    <PlatformDialog
      open={Boolean(node)}
      title={`Edit ${node ? NODE_LABELS[node.kind] : ""}`}
      onClose={onClose}
      widthClassName={node?.kind === "plant" ? "max-w-lg" : "max-w-md"}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!name.trim() || pending} onClick={submit}>
            {pending ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <FormField
        label="Name"
        required
        compact
        hint={
          node?.kind === "plant"
            ? "Equipment already assigned to this plant will be updated to the new name."
            : undefined
        }
      >
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="py-2.5 text-sm"
        />
      </FormField>

      {node?.kind === "plant" && (
        <>
          <FormField label="Code" compact>
            <TextInput
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="py-2.5 text-sm"
            />
          </FormField>
          <FormField label="Location" compact>
            <TextInput
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="py-2.5 text-sm"
            />
          </FormField>
        </>
      )}

      <label className="flex items-center gap-2.5 text-sm text-foreground cursor-pointer">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-[#FF6B00]"
        />
        <span>
          Active
          <span className="block text-xs text-muted-foreground">
            Inactive entries stay attached to existing equipment but are hidden from pickers.
          </span>
        </span>
      </label>
    </PlatformDialog>
  );
}

function DeleteNodeDialog({ node, onClose }: { node: NodeDelete | null; onClose: () => void }) {
  const deletePlant = useDeletePlant();
  const deleteArea = useDeleteArea();
  const deleteLine = useDeleteLine();

  const pending = deletePlant.isPending || deleteArea.isPending || deleteLine.isPending;
  const label = node ? NODE_LABELS[node.kind] : "";
  const blocked = (node?.equipmentCount ?? 0) > 0;

  return (
    <ConfirmDialog
      open={Boolean(node)}
      title={`Delete ${label}`}
      confirmLabel={`Delete ${label}`}
      busy={pending}
      message={
        blocked ? (
          <>
            <strong>{node?.name}</strong> still has {node?.equipmentCount} equipment record
            {node?.equipmentCount === 1 ? "" : "s"} assigned. Move or delete those first, or mark
            the {label} inactive instead — deleting will be refused.
          </>
        ) : (
          <>
            <strong>{node?.name}</strong> will be removed
            {node?.kind !== "line" && ", along with everything nested inside it"}. This cannot be
            undone.
          </>
        )
      }
      onClose={onClose}
      onConfirm={() => {
        if (!node) return;
        const options = { onSuccess: onClose };
        if (node.kind === "plant") deletePlant.mutate(node.id, options);
        else if (node.kind === "area") deleteArea.mutate(node.id, options);
        else deleteLine.mutate(node.id, options);
      }}
    />
  );
}

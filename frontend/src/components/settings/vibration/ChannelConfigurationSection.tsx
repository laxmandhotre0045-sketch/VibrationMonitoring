import React from "react";
import { Plus, Pencil, RotateCcw, SlidersHorizontal, Trash2 } from "lucide-react";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import {
  canAddChannelRow,
  canRemoveChannelRow,
  channelLabel,
} from "@/lib/vibration-settings-utils";
import type {
  ChannelAxis,
  ChannelConfig,
  ChannelDataType,
  EngineeringUnit,
} from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

const AXIS_OPTIONS: { value: ChannelAxis; label: string }[] = [
  { value: "vertical", label: "Vertical" },
  { value: "horizontal", label: "Horizontal" },
  { value: "axial", label: "Axial" },
];

const DATA_TYPE_OPTIONS: { value: ChannelDataType; label: string }[] = [
  { value: "vibration", label: "Vibration" },
  { value: "temperature", label: "Temperature" },
  { value: "velocity", label: "Velocity" },
  { value: "acceleration", label: "Acceleration" },
  { value: "displacement", label: "Displacement" },
];

const UNIT_OPTIONS: { value: EngineeringUnit; label: string }[] = [
  { value: "g", label: "g" },
  { value: "mm/s", label: "mm/s" },
  { value: "µm", label: "µm" },
  { value: "°C", label: "°C" },
];

interface ChannelConfigurationSectionProps {
  channels: ChannelConfig[];
  maxChannelCount: number;
  editingChannels: Set<number>;
  onUpdate: (channelNo: number, patch: Partial<ChannelConfig>) => void;
  onResetRow: (channelNo: number) => void;
  onToggleEdit: (channelNo: number) => void;
  onAddRow: () => void;
  onRemoveRow: (channelNo: number) => void;
}

export function ChannelConfigurationSection({
  channels,
  maxChannelCount,
  editingChannels,
  onUpdate,
  onResetRow,
  onToggleEdit,
  onAddRow,
  onRemoveRow,
}: ChannelConfigurationSectionProps) {
  const canAdd = canAddChannelRow(channels, maxChannelCount);
  const canRemove = canRemoveChannelRow(channels);

  return (
    <SettingsSectionCard
      title="Channel Configuration"
      description="Map channels to engineering information for the selected device."
      icon={<SlidersHorizontal size={22} strokeWidth={2} />}
      bodyClassName="p-0 sm:p-0"
    >
      <div className="flex flex-col gap-0 sm:flex-row sm:items-center sm:justify-between border-b border-border px-4 py-3 sm:px-5">
        <p className="text-xs font-medium text-muted-foreground">
          {channels.length} of {maxChannelCount} channel{maxChannelCount === 1 ? "" : "s"}{" "}
          configured
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          icon={<Plus size={14} />}
          disabled={!canAdd}
          onClick={onAddRow}
          className="mt-2 sm:mt-0"
        >
          Add Channel Row
        </Button>
      </div>

      {channels.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-g2 px-g4 py-g6 text-center">
          <p className="text-sm text-muted-foreground">
            No channel mappings configured. Add a row to begin mapping device channels.
          </p>
          <Button
            type="button"
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
            disabled={!canAdd}
            onClick={onAddRow}
          >
            Add Channel Row
          </Button>
        </div>
      ) : (
        <div className="overflow-x-auto max-h-[520px] overflow-y-auto rounded-b-xl">
          <table className="w-full min-w-[1080px] text-sm">
            <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur-sm border-b border-border">
              <tr className="text-left">
                <th className="px-4 py-3 font-semibold text-muted-foreground">Channel No</th>
                <th className="px-3 py-3 font-semibold text-muted-foreground">Axis</th>
                <th className="px-3 py-3 font-semibold text-muted-foreground">Data Type</th>
                <th className="px-3 py-3 font-semibold text-muted-foreground">Engineering Unit</th>
                <th className="px-3 py-3 font-semibold text-muted-foreground min-w-[180px]">
                  Measurement Point Name
                </th>
                <th className="px-3 py-3 font-semibold text-muted-foreground">Active</th>
                <th className="px-4 py-3 font-semibold text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((channel) => {
                const isEditing = editingChannels.has(channel.channelNo);
                const disabled = !isEditing;

                return (
                  <tr
                    key={channel.channelNo}
                    className={cn(
                      "border-b border-border last:border-b-0 transition-colors",
                      "hover:bg-warm/60",
                      isEditing && "bg-signal-light/5"
                    )}
                  >
                    <td className="px-4 py-2.5 font-bold text-brand whitespace-nowrap">
                      {channelLabel(channel.channelNo)}
                    </td>
                    <td className="px-3 py-2.5">
                      <select
                        className={cn(analysisSelectClass, "min-w-[120px] text-sm py-1.5")}
                        value={channel.axis}
                        disabled={disabled}
                        onChange={(event) =>
                          onUpdate(channel.channelNo, {
                            axis: event.target.value as ChannelAxis | "",
                          })
                        }
                      >
                        <option value="">Select…</option>
                        {AXIS_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <select
                        className={cn(analysisSelectClass, "min-w-[130px] text-sm py-1.5")}
                        value={channel.dataType}
                        disabled={disabled}
                        onChange={(event) =>
                          onUpdate(channel.channelNo, {
                            dataType: event.target.value as ChannelDataType | "",
                          })
                        }
                      >
                        <option value="">Select…</option>
                        {DATA_TYPE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <select
                        className={cn(analysisSelectClass, "min-w-[90px] text-sm py-1.5")}
                        value={channel.engineeringUnit}
                        disabled={disabled}
                        onChange={(event) =>
                          onUpdate(channel.channelNo, {
                            engineeringUnit: event.target.value as EngineeringUnit | "",
                          })
                        }
                      >
                        <option value="">Select…</option>
                        {UNIT_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <input
                        type="text"
                        className={cn(
                          analysisSelectClass,
                          "text-sm py-1.5",
                          disabled && "opacity-70"
                        )}
                        value={channel.measurementPointName}
                        disabled={disabled}
                        placeholder="e.g. MDE, DE, NDE"
                        onChange={(event) =>
                          onUpdate(channel.channelNo, {
                            measurementPointName: event.target.value,
                          })
                        }
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <ToggleSwitch
                        id={`channel-active-${channel.channelNo}`}
                        checked={channel.active}
                        disabled={disabled}
                        onChange={(active) => onUpdate(channel.channelNo, { active })}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Button
                          type="button"
                          variant={isEditing ? "primary" : "secondary"}
                          size="sm"
                          icon={<Pencil size={14} />}
                          onClick={() => onToggleEdit(channel.channelNo)}
                        >
                          {isEditing ? "Done" : "Edit"}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          icon={<RotateCcw size={14} />}
                          onClick={() => onResetRow(channel.channelNo)}
                        >
                          Reset Row
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          icon={<Trash2 size={14} />}
                          disabled={!canRemove}
                          onClick={() => onRemoveRow(channel.channelNo)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </SettingsSectionCard>
  );
}

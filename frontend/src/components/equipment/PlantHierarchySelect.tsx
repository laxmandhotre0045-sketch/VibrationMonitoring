import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useFormContext, Controller } from "react-hook-form";
import { FormField, SelectInput } from "@/components/ui/FormField";
import { usePlantDetail, usePlants } from "@/hooks/usePlatformSettings";
import type { EquipmentFormData } from "@/types/equipment";

/**
 * Equipment still stores plant / area / line as names — that is what every
 * filter, the dashboard grouping and the export read. These selects only
 * constrain what an operator can type, and the backend resolves the chosen
 * names back to the registry ids on save.
 *
 * A record whose saved value is not in the registry (anything predating the
 * registry, or a plant since renamed elsewhere) keeps that value as an extra
 * option, so opening an old record and saving it cannot silently blank the
 * hierarchy it was filed under.
 */
function withCurrentValue(options: string[], current: string | null | undefined): string[] {
  const value = (current ?? "").trim();
  if (!value) return options;
  const alreadyThere = options.some((option) => option.toLowerCase() === value.toLowerCase());
  return alreadyThere ? options : [...options, value];
}

export function PlantHierarchySelect() {
  const { control, watch, setValue } = useFormContext<EquipmentFormData>();

  const plantName = watch("plant_name");
  const areaName = watch("area");
  const lineName = watch("line");

  const { data: plants, isLoading: plantsLoading } = usePlants();

  const selectedPlant = useMemo(
    () =>
      plants?.find(
        (plant) => plant.name.toLowerCase() === (plantName ?? "").trim().toLowerCase()
      ) ?? null,
    [plants, plantName]
  );

  const { data: plantDetail } = usePlantDetail(selectedPlant?.id ?? null);

  const selectedArea = useMemo(
    () =>
      plantDetail?.areas.find(
        (area) => area.name.toLowerCase() === (areaName ?? "").trim().toLowerCase()
      ) ?? null,
    [plantDetail, areaName]
  );

  const plantOptions = useMemo(
    () =>
      withCurrentValue(
        (plants ?? []).filter((plant) => plant.is_active).map((plant) => plant.name),
        plantName
      ),
    [plants, plantName]
  );

  const areaOptions = useMemo(
    () =>
      withCurrentValue(
        (plantDetail?.areas ?? []).filter((area) => area.is_active).map((area) => area.name),
        areaName
      ),
    [plantDetail, areaName]
  );

  const lineOptions = useMemo(
    () =>
      withCurrentValue(
        (selectedArea?.lines ?? []).filter((line) => line.is_active).map((line) => line.name),
        lineName
      ),
    [selectedArea, lineName]
  );

  const registryEmpty = !plantsLoading && !plants?.length;

  return (
    <div className="flex flex-col gap-6">
      <FormField
        label="Plant Name"
        hint={
          registryEmpty
            ? "No plants are registered yet. Add them under Settings → Platform → Plants."
            : undefined
        }
      >
        <Controller
          name="plant_name"
          control={control}
          render={({ field }) => (
            <SelectInput
              {...field}
              value={field.value ?? ""}
              options={plantOptions}
              placeholder={plantsLoading ? "Loading plants…" : "Select plant"}
              disabled={plantsLoading || registryEmpty}
              onChange={(event) => {
                field.onChange(event.target.value);
                // Areas and lines belong to the previous plant; keeping them
                // would file the equipment under a hierarchy that never existed.
                setValue("area", "");
                setValue("line", "");
              }}
            />
          )}
        />
      </FormField>

      <FormField label="Area">
        <Controller
          name="area"
          control={control}
          render={({ field }) => (
            <SelectInput
              {...field}
              value={field.value ?? ""}
              options={areaOptions}
              placeholder={plantName ? "Select area" : "Select a plant first"}
              disabled={!plantName || (!areaOptions.length && !field.value)}
              onChange={(event) => {
                field.onChange(event.target.value);
                setValue("line", "");
              }}
            />
          )}
        />
      </FormField>

      <FormField label="Line">
        <Controller
          name="line"
          control={control}
          render={({ field }) => (
            <SelectInput
              {...field}
              value={field.value ?? ""}
              options={lineOptions}
              placeholder={areaName ? "Select line" : "Select an area first"}
              disabled={!areaName || (!lineOptions.length && !field.value)}
            />
          )}
        />
      </FormField>

      {!registryEmpty && (
        <p className="text-sm text-muted-foreground">
          Missing a plant, area or line?{" "}
          <Link to="/settings" className="font-semibold text-signal-dark hover:underline">
            Manage the hierarchy in Settings
          </Link>
          .
        </p>
      )}
    </div>
  );
}

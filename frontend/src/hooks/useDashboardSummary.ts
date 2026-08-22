import { useQuery } from "@tanstack/react-query";
import { getDashboardSummary } from "@/api/dashboard";
import { useLayout } from "@/contexts/LayoutContext";
import { ALL_PLANTS } from "@/components/layout/nav-config";

/**
 * Reads the plant selection from LayoutContext so every consumer (dashboard,
 * notification bell) stays scoped to the same plant without threading the
 * value through each call site.
 */
export function useDashboardSummary() {
  const { selectedPlant } = useLayout();
  const plantFilter = selectedPlant === ALL_PLANTS ? undefined : selectedPlant;

  return useQuery({
    queryKey: ["dashboard-summary", plantFilter ?? "all"],
    queryFn: () => getDashboardSummary(plantFilter),
    retry: 1,
    refetchInterval: 60_000,
  });
}

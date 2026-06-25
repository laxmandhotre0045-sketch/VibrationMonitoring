import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Search,
  Cpu,
  Trash2,
  Edit2,
  Filter,
  MoreHorizontal,
  Activity,
} from "lucide-react";
import { listEquipment, deleteEquipment } from "@/api/equipment";
import { CRITICALITY_COLORS, CRITICALITY_DOT, ASSET_STATUS_COLORS } from "@/types/equipment";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { WRITE_ROLES } from "@/lib/role-access";
import { emptyEquipment } from "@/images";
import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { EquipmentPageShell } from "@/components/equipment/EquipmentPageShell";
import { cardSizing } from "@/lib/card-sizing";
import { cardHover } from "@/lib/card-hover";

const MACHINE_TYPES = [
  "", "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
  "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
];
const CRITICALITY = ["", "Low", "Medium", "High", "Critical"];

const STAT_CONFIG = [
  { key: "total", label: "Total Equipment", iconBg: "bg-white border border-border", iconColor: "text-signal-dark" },
  { key: "critical", label: "Critical Assets", iconBg: "bg-white border border-border", iconColor: "text-machine-critical" },
  { key: "high", label: "High Priority", iconBg: "bg-white border border-border", iconColor: "text-signal-dark" },
  { key: "active", label: "Active Status", iconBg: "bg-machine-healthy/10", iconColor: "text-machine-healthy" },
] as const;

export function EquipmentMasterList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterCriticality, setFilterCriticality] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["equipment", page, filterType, filterCriticality],
    queryFn: () =>
      listEquipment({
        page,
        page_size: 20,
        machine_type: filterType || undefined,
        machine_criticality: filterCriticality || undefined,
      }),
  });

  const { hasRole } = useAuth();
  const canWrite = hasRole(WRITE_ROLES);

  const deleteMutation = useMutation({
    mutationFn: deleteEquipment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["equipment"] });
      showToast("Equipment deleted.", "success");
    },
    onError: () => showToast("Failed to delete equipment.", "error"),
  });

  const filtered =
    data?.items.filter(
      (item) =>
        !search ||
        item.machine_name.toLowerCase().includes(search.toLowerCase()) ||
        item.machine_id.toLowerCase().includes(search.toLowerCase()) ||
        item.plant_name.toLowerCase().includes(search.toLowerCase())
    ) || [];

  const handleDelete = (id: string, name: string) => {
    if (confirm(`Delete "${name}"? This cannot be undone.`)) {
      deleteMutation.mutate(id);
    }
  };

  const stats = {
    total: data?.total || 0,
    critical: data?.items.filter((i) => i.machine_criticality === "Critical").length || 0,
    high: data?.items.filter((i) => i.machine_criticality === "High").length || 0,
    active: data?.items.filter((i) => i.asset_status === "Active").length || 0,
  };

  return (
    <EquipmentPageShell>
    <div>
      <PageHero
        title="Equipment Master"
        subtitle="Configure equipment profiles and digital twins for vibration monitoring."
        vibrationBg
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Equipment Master" },
        ]}
        equipmentCount={stats.total}
        actions={
          canWrite ? (
            <Button
              size="lg"
              icon={<Plus size={18} />}
              onClick={() => navigate("/equipment/new")}
            >
              Add Equipment
            </Button>
          ) : undefined
        }
      />

      {/* Stats */}
      <div className={cn("grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8", cardSizing.gridEqual)}>
        {STAT_CONFIG.map((stat, i) => (
          <GlassCard key={stat.key} equalHeight delay={0.05 + i * 0.06} className="p-5">
            <div className={cn(cardSizing.kpiBody, "gap-4")}>
              <div className={cn("w-11 h-11 rounded-lg flex items-center justify-center", stat.iconBg)}>
                <Cpu size={18} className={stat.iconColor} />
              </div>
              <div>
                <p className="text-kpi-value">
                  {stats[stat.key]}
                </p>
                <p className="text-base font-medium text-muted-foreground">
                  {stat.label}
                </p>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Filters */}
      <GlassCard className="p-4 mb-6" delay={0.2}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search
              size={16}
              className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, ID, or plant..."
              className={cn(
                "w-full pl-11 pr-4 py-2.5 text-base font-normal rounded-lg transition-all",
                "bg-white border border-border text-foreground",
                "placeholder:text-placeholder placeholder:font-normal focus:outline-none",
                "focus:border-brand-accent focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]"
              )}
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter size={15} className="text-brand hidden sm:block" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className={cn(
                "px-4 py-2.5 text-base font-normal rounded-lg cursor-pointer transition-all",
                "bg-white border border-border text-foreground",
                "focus:outline-none focus:border-brand-accent focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]"
              )}
            >
              <option value="">All Types</option>
              {MACHINE_TYPES.slice(1).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={filterCriticality}
              onChange={(e) => setFilterCriticality(e.target.value)}
              className={cn(
                "px-4 py-2.5 text-base font-normal rounded-lg cursor-pointer transition-all",
                "bg-white border border-border text-foreground",
                "focus:outline-none focus:border-brand-accent focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]"
              )}
            >
              <option value="">All Criticality</option>
              {CRITICALITY.slice(1).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>
      </GlassCard>

      {/* Equipment Table */}
      <GlassCard className="overflow-hidden" delay={0.35}>
        {isLoading ? (
          <div className={cn(cardSizing.stateCenter, "gap-4")}>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="w-10 h-10 rounded-lg border-2 border-signal-light border-t-transparent"
            />
            <p className="text-helper">Loading equipment registry...</p>
          </div>
        ) : isError ? (
          <div className={cn(cardSizing.stateCenter, "text-center")}>
            <p className="font-bold text-destructive">Failed to load equipment.</p>
            <p className="text-helper mt-2">
              Make sure the backend is running on port 8000.
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <div className={cn(cardSizing.stateCenter, "text-center")}>
            <img
              src={emptyEquipment}
              alt=""
              className="w-24 h-24 mx-auto mb-4 opacity-80"
            />
            <p className="font-semibold text-foreground text-lg">
              No equipment found.
            </p>
            <p className="text-helper mt-1">
              Add your first equipment to begin AI readiness configuration.
            </p>
            {canWrite && (
              <div className="mt-6">
                <Button icon={<Plus size={16} />} onClick={() => navigate("/equipment/new")}>
                  Add Equipment
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className={cardSizing.scroll}>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  {["Machine", "ID", "Type", "Plant / Area", "Criticality", "Status", "Actions"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left text-table-header px-5 py-4 whitespace-nowrap"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {filtered.map((item, i) => (
                    <motion.tr
                      key={item.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03 }}
                      className="border-b border-border/50 hover:bg-warm transition-colors group"
                    >
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-white border border-border flex items-center justify-center shrink-0 group-hover:border-signal-light/50 transition-colors">
                            <Cpu size={16} className="text-brand" />
                          </div>
                          <div>
                            <p className="text-base font-semibold text-foreground">
                              {item.machine_name}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              {item.manufacturer || "—"}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className="text-sm font-mono px-2.5 py-1 rounded-xl bg-white text-foreground border border-border">
                          {item.machine_id}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-base text-foreground/90">
                        {item.machine_type}
                      </td>
                      <td className="px-5 py-4">
                        <p className="text-base text-foreground/90">
                          {item.plant_name}
                        </p>
                        <p className="text-sm text-muted-foreground">{item.area}</p>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-full border",
                            CRITICALITY_COLORS[item.machine_criticality]
                          )}
                        >
                          <span
                            className={cn(
                              "w-1.5 h-1.5 rounded-full",
                              CRITICALITY_DOT[item.machine_criticality]
                            )}
                          />
                          {item.machine_criticality}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={cn(
                            "text-sm px-3 py-1.5 rounded-full font-semibold",
                            ASSET_STATUS_COLORS[item.asset_status || "Active"] ||
                              ASSET_STATUS_COLORS.Active
                          )}
                        >
                          {item.asset_status || "Active"}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                          {canWrite && (
                            <>
                              <motion.button
                                whileTap={{ scale: 0.9 }}
                                onClick={() => navigate(`/equipment/${item.id}/edit`)}
                                className="p-2 text-muted-foreground hover:text-signal-deep hover:bg-warm rounded-xl transition-colors"
                                title="Edit"
                              >
                                <Edit2 size={15} />
                              </motion.button>
                              <motion.button
                                whileTap={{ scale: 0.9 }}
                                onClick={() => handleDelete(item.id, item.machine_name)}
                                className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-xl transition-colors"
                                title="Delete"
                              >
                                <Trash2 size={15} />
                              </motion.button>
                            </>
                          )}
                          <button className="p-2 text-muted-foreground hover:text-foreground rounded-xl transition-colors">
                            <MoreHorizontal size={15} />
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* Pagination */}
      {data && data.total > 20 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-between mt-6"
        >
          <p className="text-base text-muted-foreground">
            Showing {Math.min((page - 1) * 20 + 1, data.total)}–
            {Math.min(page * 20, data.total)} of {data.total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={page * 20 >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </motion.div>
      )}

      {/* AI hint */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className={cn(
          "mt-8 flex items-center gap-3 px-5 py-4 rounded-lg bg-brand-accent/5 orange-gradient-border-subtle",
          cardHover.passive
        )}
      >
        <Activity size={18} className="text-brand-accent-dark shrink-0" />
        <p className="text-helper">
          <span className="font-semibold text-foreground">
            AI Tip:
          </span>{" "}
          Complete sensor orientation and operating parameters to maximize AI diagnostic accuracy.
        </p>
      </motion.div>
    </div>
    </EquipmentPageShell>
  );
}

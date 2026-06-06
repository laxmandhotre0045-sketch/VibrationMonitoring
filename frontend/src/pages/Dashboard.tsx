import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Filter, Cpu, Trash2, Edit2, MoreVertical, Activity } from "lucide-react";
import { listEquipment, deleteEquipment } from "@/api/equipment";
import { CRITICALITY_COLORS, CRITICALITY_DOT } from "@/types/equipment";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/Toast";

const MACHINE_TYPES = [
  "", "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
  "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
];
const CRITICALITY = ["", "Low", "Medium", "High", "Critical"];

export function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterCriticality, setFilterCriticality] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["equipment", page, filterType, filterCriticality],
    queryFn: () => listEquipment({ page, page_size: 20, machine_type: filterType || undefined, machine_criticality: filterCriticality || undefined }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteEquipment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["equipment"] });
      showToast("Equipment deleted.", "success");
    },
    onError: () => showToast("Failed to delete equipment.", "error"),
  });

  const filtered = data?.items.filter((item) =>
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

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-20 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center shadow-sm">
            <Activity size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">AI Vibration Intelligence Platform</h1>
            <p className="text-xs text-gray-500">Equipment Master Data — Stage 1</p>
          </div>
        </div>
        <button
          onClick={() => navigate("/equipment/new")}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-all shadow-sm"
        >
          <Plus size={16} /> Add Equipment
        </button>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Stats Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[
            { label: "Total Equipment", value: data?.total || 0, color: "text-blue-600", bg: "bg-blue-50" },
            { label: "Critical", value: data?.items.filter((i) => i.machine_criticality === "Critical").length || 0, color: "text-purple-600", bg: "bg-purple-50" },
            { label: "High", value: data?.items.filter((i) => i.machine_criticality === "High").length || 0, color: "text-red-600", bg: "bg-red-50" },
            { label: "Active", value: data?.items.filter((i) => i.asset_status === "Active").length || 0, color: "text-green-600", bg: "bg-green-50" },
          ].map((stat) => (
            <div key={stat.label} className={cn("rounded-xl p-4 border border-gray-200 bg-white flex items-center gap-3")}>
              <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", stat.bg)}>
                <Cpu size={18} className={stat.color} />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                <p className="text-xs text-gray-500">{stat.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-5">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, ID, or plant..."
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Types</option>
            {MACHINE_TYPES.slice(1).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select
            value={filterCriticality}
            onChange={(e) => setFilterCriticality(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Criticality</option>
            {CRITICALITY.slice(1).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* Equipment Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <svg className="animate-spin h-8 w-8 text-blue-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
            </div>
          ) : isError ? (
            <div className="text-center py-20 text-red-500">
              <p className="font-medium">Failed to load equipment.</p>
              <p className="text-sm text-gray-400 mt-1">Make sure the backend is running on port 8000.</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <Cpu size={40} className="mx-auto mb-3 text-gray-200" />
              <p className="font-medium text-gray-500">No equipment found.</p>
              <p className="text-sm mt-1">Add your first equipment to get started.</p>
              <button
                onClick={() => navigate("/equipment/new")}
                className="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
              >
                + Add Equipment
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    {["Machine", "ID", "Type", "Plant / Area", "Criticality", "Status", "Actions"].map((h) => (
                      <th key={h} className="text-left text-xs font-semibold text-gray-500 px-4 py-3 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {filtered.map((item) => (
                    <tr key={item.id} className="hover:bg-blue-50/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
                            <Cpu size={14} className="text-blue-600" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-900">{item.machine_name}</p>
                            <p className="text-xs text-gray-400">{item.manufacturer || "—"}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded text-gray-700">{item.machine_id}</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">{item.machine_type}</td>
                      <td className="px-4 py-3">
                        <p className="text-sm text-gray-700">{item.plant_name}</p>
                        <p className="text-xs text-gray-400">{item.area}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn("inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border", CRITICALITY_COLORS[item.machine_criticality])}>
                          <span className={cn("w-1.5 h-1.5 rounded-full", CRITICALITY_DOT[item.machine_criticality])} />
                          {item.machine_criticality}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full font-medium",
                          item.asset_status === "Active" ? "bg-green-100 text-green-700" :
                          item.asset_status === "Under Maintenance" ? "bg-yellow-100 text-yellow-700" :
                          "bg-gray-100 text-gray-600"
                        )}>
                          {item.asset_status || "Active"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => navigate(`/equipment/${item.id}/edit`)}
                            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                            title="Edit"
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(item.id, item.machine_name)}
                            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            title="Delete"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {data && data.total > 20 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">
              Showing {Math.min((page - 1) * 20 + 1, data.total)}–{Math.min(page * 20, data.total)} of {data.total}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * 20 >= data.total}
                className="px-3 py-1.5 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

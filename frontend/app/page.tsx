"use client";

import { useState, useEffect, useCallback } from "react";
import { api, Business } from "@/lib/api";
import LeadTable from "@/components/LeadTable";
import ResearchForm from "@/components/ResearchForm";

const PRIORITIES = ["", "HOT", "HIGH", "MEDIUM", "LOW"];
const SORT_OPTIONS = [
  { value: "final_score", label: "Deskie Score" },
  { value: "review_count", label: "Reviews" },
  { value: "rating", label: "Rating" },
];

export default function DashboardPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Filters
  const [priority, setPriority] = useState("");
  const [sortBy, setSortBy] = useState("final_score");
  const [cityFilter, setCityFilter] = useState("");

  const loadBusinesses = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listBusinesses({
        priority: priority || undefined,
        sort_by: sortBy,
        city: cityFilter || undefined,
        limit: 100,
      });
      setBusinesses(data.businesses);
      setTotal(data.total);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [priority, sortBy, cityFilter]);

  useEffect(() => {
    loadBusinesses();
  }, [loadBusinesses]);

  const handleExportCSV = () => {
    if (businesses.length === 0) return;
    const headers = [
      "Business Name", "City", "Category", "Score", "Priority", "Pitch Angle", 
      "Qualification Reason", "Email", "Phone", "Website", "Pain Score", "Value Score", "Digital Score", "Timing Score"
    ];
    
    const rows = businesses.map(b => [
      `"${(b.name || "").replace(/"/g, '""')}"`,
      `"${(b.city || "").replace(/"/g, '""')}"`,
      `"${(b.category || "").replace(/"/g, '""')}"`,
      b.score?.final_score || "",
      b.score?.priority || "",
      `"${(b.score?.pitch_angle || "").replace(/"/g, '""')}"`,
      `"${(b.score?.qualification_reason || "").replace(/"/g, '""')}"`,
      `"${(b.email || "").replace(/"/g, '""')}"`,
      `"${(b.phone || "").replace(/"/g, '""')}"`,
      `"${(b.website || "").replace(/"/g, '""')}"`,
      b.score?.pain_score || "",
      b.score?.business_value_score || "",
      b.score?.digital_score || "",
      b.score?.timing_score || "",
    ]);
    
    const csvContent = [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `deskie-leads-${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const hotCount = businesses.filter((b) => b.score?.priority === "HOT").length;
  const highCount = businesses.filter((b) => b.score?.priority === "HIGH").length;
  const avgScore =
    businesses.length > 0
      ? businesses.reduce((a, b) => a + (b.score?.final_score ?? 0), 0) / businesses.length
      : 0;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      {/* Header */}
      <header className="border-b border-white/10 bg-white/5 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-sm">
              D
            </div>
            <div>
              <h1 className="font-semibold text-white text-sm leading-none">
                Deskie LIE
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">Lead Intelligence Engine</p>
            </div>
          </div>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + New Research
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {/* Research Form */}
        {showForm && (
          <ResearchForm
            onComplete={() => {
              setShowForm(false);
              loadBusinesses();
            }}
          />
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Total Leads", value: total, color: "text-white" },
            { label: "HOT Leads", value: hotCount, color: "text-red-400" },
            { label: "HIGH Leads", value: highCount, color: "text-orange-400" },
            { label: "Avg Score", value: avgScore.toFixed(1), color: "text-indigo-400" },
          ].map((stat) => (
            <div
              key={stat.label}
              className="bg-white/5 border border-white/10 rounded-xl p-4"
            >
              <p className="text-xs text-slate-400 uppercase tracking-wide font-medium">
                {stat.label}
              </p>
              <p className={`text-3xl font-bold mt-1 ${stat.color}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 items-center">
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">All Priorities</option>
            {PRIORITIES.filter(Boolean).map((p) => (
              <option key={p} value={p} className="bg-slate-900">{p}</option>
            ))}
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-slate-900">{o.label}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Filter by city..."
            value={cityFilter}
            onChange={(e) => setCityFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-40"
          />

          <button
            onClick={loadBusinesses}
            className="text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 border border-white/10 rounded-lg hover:border-white/20"
          >
            ↺ Refresh
          </button>

          <button
            onClick={handleExportCSV}
            className="text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 border border-white/10 rounded-lg hover:border-white/20 flex items-center gap-1 ml-auto"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
            Export CSV
          </button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500">
            <span className="animate-spin text-2xl mr-3">⟳</span> Loading leads...
          </div>
        ) : (
          <LeadTable businesses={businesses} />
        )}
      </main>
    </div>
  );
}

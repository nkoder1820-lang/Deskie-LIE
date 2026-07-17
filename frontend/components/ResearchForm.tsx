"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const INDUSTRIES = [
  { key: "dental_clinics", label: "Dental Clinics" },
  { key: "dermatology_clinics", label: "Dermatology Clinics" },
  { key: "cosmetic_clinics", label: "Cosmetic Clinics" },
  { key: "fertility_clinics", label: "Fertility Clinics" },
  { key: "real_estate", label: "Real Estate" },
  { key: "coaching_institutes", label: "Coaching Institutes" },
  { key: "premium_salons", label: "Premium Salons" },
];

const CITIES = [
  "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
  "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Surat",
];

interface Props {
  onComplete: () => void;
}

export default function ResearchForm({ onComplete }: Props) {
  const [industry, setIndustry] = useState("dental_clinics");
  const [city, setCity] = useState("Mumbai");
  const [maxResults, setMaxResults] = useState(10);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);

    try {
      const result = await api.runResearch({ industry, city, max_results: maxResults });
      setStatus({
        type: "success",
        msg: `✅ ${result.message} — ${result.leads_count} leads discovered`,
      });
      onComplete();
    } catch (err) {
      setStatus({
        type: "error",
        msg: `❌ ${err instanceof Error ? err.message : "Research failed"}`,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-white mb-1">New Research Job</h2>
      <p className="text-sm text-slate-400 mb-5">
        Discover and score leads for an industry + city combination.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              Industry
            </label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            >
              {INDUSTRIES.map((i) => (
                <option key={i.key} value={i.key} className="bg-slate-900">
                  {i.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              City
            </label>
            <select
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            >
              {CITIES.map((c) => (
                <option key={c} value={c} className="bg-slate-900">
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              Max Results
            </label>
            <input
              type="number"
              min={1}
              max={60}
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 disabled:text-indigo-400 text-white font-medium rounded-lg text-sm transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <span className="animate-spin text-base">⟳</span>
                Researching...
              </>
            ) : (
              "🔍 Run Research"
            )}
          </button>
          {loading && (
            <p className="text-xs text-slate-400 animate-pulse">
              Discovering businesses and running all agents... this may take a minute.
            </p>
          )}
        </div>

        {status && (
          <div
            className={`text-sm px-4 py-3 rounded-lg ${
              status.type === "success"
                ? "bg-green-500/15 text-green-400 border border-green-500/30"
                : "bg-red-500/15 text-red-400 border border-red-500/30"
            }`}
          >
            {status.msg}
          </div>
        )}
      </form>
    </div>
  );
}

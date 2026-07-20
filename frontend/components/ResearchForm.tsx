"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const INDUSTRY_SUGGESTIONS = [
  "dental clinics", "med spas", "dermatology clinics", "cosmetic clinics",
  "fertility clinics", "veterinary clinics", "chiropractors", "law firms",
  "HVAC services", "plumbers", "roofing contractors", "auto repair",
  "real estate", "property management", "coaching institutes", "premium salons",
  "restaurants", "fine dining restaurants",
];

const CITY_SUGGESTIONS = [
  // India
  "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Pune",
  // USA
  "New York", "Los Angeles", "Chicago", "Houston", "Austin, TX", "Miami",
  "Dallas", "San Francisco", "Seattle", "Boston", "Atlanta", "Phoenix",
  // Global
  "London", "Toronto", "Sydney", "Dubai", "Singapore",
];

const COUNTRIES = ["", "India", "USA", "UK", "Canada", "Australia", "UAE", "Singapore"];

interface Props {
  onComplete: () => void;
}

export default function ResearchForm({ onComplete }: Props) {
  const [bulkMode, setBulkMode] = useState(false);
  const [industry, setIndustry] = useState("dental clinics");
  const [city, setCity] = useState("Mumbai");
  const [country, setCountry] = useState("");
  const [maxResults, setMaxResults] = useState(10);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [bulkProgress, setBulkProgress] = useState<string | null>(null);

  async function pollBulk() {
    // Poll until the background job completes, refreshing the table as leads land
    for (;;) {
      await new Promise((r) => setTimeout(r, 5000));
      try {
        const s = await api.bulkStatus();
        if (s.status === "running") {
          setBulkProgress(
            `${s.pairs_done}/${s.total_pairs} searches done — ${s.leads_found} leads so far` +
            (s.current ? ` (now: ${s.current})` : "")
          );
          onComplete();
        } else {
          setBulkProgress(null);
          setStatus({
            type: "success",
            msg: `✅ Bulk research complete — ${s.leads_found ?? 0} leads found` +
              (s.errors?.length ? ` (${s.errors.length} searches failed)` : ""),
          });
          onComplete();
          return;
        }
      } catch {
        // backend briefly unreachable — keep polling
      }
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);

    try {
      if (bulkMode) {
        const industries = industry.split(",").map((s) => s.trim()).filter(Boolean);
        const cities = city.split(",").map((s) => s.trim()).filter(Boolean);
        const result = await api.runBulkResearch({
          industries,
          cities,
          country: country || undefined,
          max_results_per_pair: maxResults,
        });
        setStatus({
          type: "success",
          msg: `🚀 Bulk job started: ${result.pairs} searches, up to ${result.max_leads} leads. Leads appear in the table as they land.`,
        });
        setLoading(false);
        pollBulk();
        return;
      }
      const result = await api.runResearch({
        industry,
        city,
        country: country || undefined,
        max_results: maxResults,
      });
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
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold text-white">New Research Job</h2>
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={bulkMode}
            onChange={(e) => setBulkMode(e.target.checked)}
            className="accent-indigo-600"
          />
          Bulk mode (1000s of leads)
        </label>
      </div>
      <p className="text-sm text-slate-400 mb-5">
        {bulkMode
          ? "Comma-separate multiple industries and cities — every combination is researched in the background."
          : "Discover and score leads for any industry, in any city worldwide. Type freely — suggestions are optional."}
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className={bulkMode ? "sm:col-span-2" : ""}>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              {bulkMode ? "Industries (comma-separated)" : "Industry / Niche"}
            </label>
            <input
              type="text"
              list="industry-suggestions"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder={bulkMode ? "restaurants, med spas, dental clinics" : "e.g. med spas, law firms..."}
              required
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <datalist id="industry-suggestions">
              {INDUSTRY_SUGGESTIONS.map((i) => (
                <option key={i} value={i} />
              ))}
            </datalist>
          </div>

          <div className={bulkMode ? "sm:col-span-2" : ""}>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              {bulkMode ? "Cities (comma-separated)" : "City"}
            </label>
            <input
              type="text"
              list="city-suggestions"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder={bulkMode ? "Austin TX, Miami, Dallas" : "e.g. Austin, TX"}
              required
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <datalist id="city-suggestions">
              {CITY_SUGGESTIONS.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              Country
            </label>
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            >
              {COUNTRIES.map((c) => (
                <option key={c} value={c} className="bg-slate-900">
                  {c || "Auto-detect"}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">
              {bulkMode ? "Max per search" : "Max Results"}
            </label>
            <input
              type="number"
              min={1}
              max={300}
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
              Discovering businesses and running all agents... this may take a few minutes.
            </p>
          )}
          {bulkProgress && (
            <p className="text-xs text-indigo-300 animate-pulse">🚀 {bulkProgress}</p>
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

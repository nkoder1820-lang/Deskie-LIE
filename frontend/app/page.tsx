"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api, Business, outreachLinks, pocOutreachLinks } from "@/lib/api";
import LeadTable from "@/components/LeadTable";
import ResearchForm from "@/components/ResearchForm";

const PRIORITIES = ["", "HOT", "HIGH", "MEDIUM", "LOW"];
const SORT_OPTIONS = [
  { value: "final_score", label: "Deskie Score" },
  { value: "review_count", label: "Reviews" },
  { value: "rating", label: "Rating" },
];

// LIE doesn't store a country column — infer it from the phone prefix
// (E.164 from Google Places), longest prefix first so +971 wins over +91.
const COUNTRY_PREFIXES: [string, string][] = [
  ["+971", "🇦🇪 UAE"], ["+353", "🇮🇪 Ireland"], ["+91", "🇮🇳 India"],
  ["+44", "🇬🇧 UK"], ["+61", "🇦🇺 Australia"], ["+65", "🇸🇬 Singapore"],
  ["+64", "🇳🇿 New Zealand"], ["+1", "🇺🇸 USA / Canada"],
];

function inferCountry(b: Business): string {
  for (const raw of [b.phone, ...(b.phones || [])]) {
    const p = (raw || "").replace(/[\s()-]/g, "");
    if (!p.startsWith("+")) continue;
    const hit = COUNTRY_PREFIXES.find(([prefix]) => p.startsWith(prefix));
    if (hit) return hit[1];
  }
  return "Other";
}

function prettyCategory(c: string): string {
  return (c || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

export default function DashboardPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Filters — applied client-side over one full fetch (backend caps at 200
  // rows), so every dropdown change is instant and options self-populate
  // from the actual data.
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [sortBy, setSortBy] = useState("final_score");
  const [cityFilter, setCityFilter] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [demoFilter, setDemoFilter] = useState("");

  // Bulk PoC research
  const [pocBulkLoading, setPocBulkLoading] = useState(false);
  const [pocBulkMsg, setPocBulkMsg] = useState<string | null>(null);

  const loadBusinesses = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listBusinesses({ sort_by: "final_score", limit: 200 });
      setBusinesses(data.businesses);
      setTotal(data.total);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBusinesses();
  }, [loadBusinesses]);

  // Dropdown options, derived from the loaded data.
  const cityOptions = useMemo(
    () => [...new Set(businesses.map((b) => b.city).filter(Boolean))].sort(),
    [businesses],
  );
  // Filter on prettified labels so raw variants ("med spas" / "med_spas")
  // collapse into one option.
  const categoryOptions = useMemo(
    () => [...new Set(businesses.map((b) => prettyCategory(b.category)).filter(Boolean))].sort(),
    [businesses],
  );
  const countryOptions = useMemo(
    () => [...new Set(businesses.map(inferCountry))].sort(),
    [businesses],
  );

  const displayed = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = businesses.filter((b) => {
      if (q && !(b.name || "").toLowerCase().includes(q)) return false;
      if (cityFilter && b.city !== cityFilter) return false;
      if (countryFilter && inferCountry(b) !== countryFilter) return false;
      if (categoryFilter && prettyCategory(b.category) !== categoryFilter) return false;
      if (priority && b.score?.priority !== priority) return false;
      if (demoFilter === "yes" && !b.demo_url) return false;
      if (demoFilter === "no" && b.demo_url) return false;
      return true;
    });
    return filtered.sort((a, b) => {
      if (sortBy === "rating") return (b.rating ?? -1) - (a.rating ?? -1);
      if (sortBy === "review_count") return (b.review_count ?? -1) - (a.review_count ?? -1);
      return (b.score?.final_score ?? -1) - (a.score?.final_score ?? -1);
    });
  }, [businesses, search, cityFilter, countryFilter, categoryFilter, priority, demoFilter, sortBy]);

  const filtersActive = !!(search || cityFilter || countryFilter || categoryFilter || priority || demoFilter);
  const clearFilters = () => {
    setSearch(""); setCityFilter(""); setCountryFilter("");
    setCategoryFilter(""); setPriority(""); setDemoFilter("");
  };

  const handleBulkResearchPoc = async () => {
    const withoutPoc = businesses.filter((b) => !b.poc_researched_at).length;
    if (
      !window.confirm(
        `Research decision-maker contacts for up to 20 leads that haven't been researched yet ` +
        `(${withoutPoc} of ${businesses.length} on this page)?\n\n` +
        `This uses SerpAPI web-search quota (~2 searches/lead) — your free tier is limited.`
      )
    ) {
      return;
    }
    setPocBulkLoading(true);
    setPocBulkMsg(null);
    try {
      const r = await api.researchPocBulk(undefined, 20);
      setPocBulkMsg(`✅ Researched ${r.succeeded}/${r.targeted} leads`);
      loadBusinesses();
    } catch (e) {
      setPocBulkMsg(`❌ ${e instanceof Error ? e.message : "Bulk PoC research failed"}`);
    } finally {
      setPocBulkLoading(false);
    }
  };

  // Exports the filtered view — what you see is what you get.
  const handleExportCSV = () => {
    if (displayed.length === 0) return;
    const q = (v: string | null | undefined) => `"${(v || "").replace(/"/g, '""')}"`;
    const headers = [
      "Business Name", "City", "Category", "Score", "Priority", "Pitch Angle",
      "Pitch Reason Source Label", "Pitch Reason Source Link", "Evidence Sources (all)",
      "Qualification Reason", "Email", "All Emails", "Phone", "All Phones",
      "WhatsApp", "Website", "Instagram", "Facebook", "LinkedIn", "Twitter/X",
      "YouTube", "Google Maps", "Contact Form", "LinkedIn People Search",
      "Outreach Subject", "Outreach Email", "WhatsApp Message",
      "Send Email Link (prefilled)", "Send WhatsApp Link (prefilled)",
      "Send SMS Link (prefilled)", "Messenger Link",
      // Decision-maker (PoC) columns
      "PoC 1 Name", "PoC 1 Title", "PoC 1 Confidence", "PoC 1 Email", "PoC 1 Guessed Email",
      "PoC 1 Phone", "PoC 1 LinkedIn", "PoC 1 Send Email Link", "PoC 1 Send WhatsApp Link",
      "PoC 2 Name", "PoC 2 Title", "PoC 2 Confidence", "PoC 2 Email", "PoC 2 Guessed Email",
      "PoC 2 Phone", "PoC 2 LinkedIn", "PoC 2 Send Email Link", "PoC 2 Send WhatsApp Link",
      "PoC 3 Name", "PoC 3 Title", "PoC 3 Confidence", "PoC 3 Email", "PoC 3 Guessed Email",
      "PoC 3 Phone", "PoC 3 LinkedIn", "PoC 3 Send Email Link", "PoC 3 Send WhatsApp Link",
      "Pain Score", "Value Score", "Digital Score", "Timing Score"
    ];

    const rows = displayed.map(b => {
      const send = outreachLinks(b);
      const pocCols: (string | number)[] = [];
      for (let i = 0; i < 3; i++) {
        const poc = b.poc_contacts?.[i];
        if (!poc) {
          pocCols.push(q(null), q(null), q(null), q(null), q(null), q(null), q(null), q(null), q(null));
          continue;
        }
        const draft = b.report?.poc_outreach?.find((d) => d.name === poc.name);
        const pocLinks = pocOutreachLinks(poc, draft, b);
        pocCols.push(
          q(poc.name), q(poc.title), q(poc.confidence),
          q(poc.emails[0]), q(poc.guessed_emails[0]), q(poc.phones[0]), q(poc.linkedin_url),
          q(pocLinks.email), q(pocLinks.whatsapp),
        );
      }
      return [
      q(b.name),
      q(b.city),
      q(b.category),
      b.score?.final_score || "",
      b.score?.priority || "",
      q(b.score?.pitch_angle),
      q(b.score?.pitch_source?.label),
      q(b.score?.pitch_source?.url),
      q((b.report?.sources || []).map((s) => `${s.label}: ${s.url}`).join(" | ")),
      q(b.score?.qualification_reason),
      q(b.email),
      q((b.emails || []).join("; ")),
      q(b.phone),
      q((b.phones || []).join("; ")),
      q(b.whatsapp),
      q(b.website),
      q(b.social_links?.instagram),
      q(b.social_links?.facebook),
      q(b.social_links?.linkedin),
      q(b.social_links?.twitter),
      q(b.social_links?.youtube),
      q(b.maps_url || b.social_links?.google_maps),
      q(b.contact_form_url),
      q(b.linkedin_search),
      q(b.report?.outreach_subject),
      q(b.report?.outreach_email),
      q(b.report?.whatsapp_message),
      q(send.email),
      q(send.whatsapp),
      q(send.sms),
      q(send.messenger),
      ...pocCols,
      b.score?.pain_score || "",
      b.score?.business_value_score || "",
      b.score?.digital_score || "",
      b.score?.timing_score || "",
    ];
    });
    
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
          <input
            type="text"
            placeholder="🔍 Search business..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-48"
          />

          <select
            value={cityFilter}
            onChange={(e) => setCityFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">All Cities</option>
            {cityOptions.map((c) => (
              <option key={c} value={c} className="bg-slate-900">{c}</option>
            ))}
          </select>

          <select
            value={countryFilter}
            onChange={(e) => setCountryFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">All Countries</option>
            {countryOptions.map((c) => (
              <option key={c} value={c} className="bg-slate-900">{c}</option>
            ))}
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">All Business Types</option>
            {categoryOptions.map((c) => (
              <option key={c} value={c} className="bg-slate-900">{c}</option>
            ))}
          </select>

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
            value={demoFilter}
            onChange={(e) => setDemoFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">Demo: Any</option>
            <option value="yes" className="bg-slate-900">Demo Created</option>
            <option value="no" className="bg-slate-900">No Demo Yet</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-slate-900">Sort: {o.label}</option>
            ))}
          </select>

          {filtersActive && (
            <button
              onClick={clearFilters}
              className="text-xs text-indigo-300 hover:text-indigo-200 transition-colors px-3 py-1.5 border border-indigo-500/40 rounded-lg"
            >
              ✕ Clear filters
            </button>
          )}

          <button
            onClick={loadBusinesses}
            className="text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 border border-white/10 rounded-lg hover:border-white/20"
          >
            ↺ Refresh
          </button>

          <button
            onClick={handleBulkResearchPoc}
            disabled={pocBulkLoading}
            title="Find decision-maker names, titles and contact details for leads that don't have them yet. Uses SerpAPI quota."
            className="text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 border border-white/10 rounded-lg hover:border-white/20 flex items-center gap-1 ml-auto disabled:opacity-50"
          >
            {pocBulkLoading ? (
              <>
                <span className="animate-spin">⟳</span> Researching decision makers...
              </>
            ) : (
              "🔎 Research decision makers"
            )}
          </button>

          <button
            onClick={handleExportCSV}
            className="text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 border border-white/10 rounded-lg hover:border-white/20 flex items-center gap-1"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
            Export CSV
          </button>
        </div>

        {pocBulkMsg && (
          <p className="text-xs text-slate-400 -mt-3">{pocBulkMsg}</p>
        )}

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500">
            <span className="animate-spin text-2xl mr-3">⟳</span> Loading leads...
          </div>
        ) : (
          <>
            {filtersActive && (
              <p className="text-xs text-slate-400 -mt-2">
                Showing {displayed.length} of {businesses.length} leads
              </p>
            )}
            <LeadTable businesses={displayed} />
          </>
        )}
      </main>
    </div>
  );
}

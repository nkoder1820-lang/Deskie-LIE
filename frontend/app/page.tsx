"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api, Business, outreachLinks, pocOutreachLinks } from "@/lib/api";
import LeadTable from "@/components/LeadTable";
import ResearchForm from "@/components/ResearchForm";

const PRIORITIES = ["", "HOT", "HIGH", "MEDIUM", "LOW"];
const SORT_OPTIONS = [
  // Default: ICP fit first (good > borderline > excluded), hiring-discovered
  // leads before industry-searched within each band, then Deskie score.
  { value: "best_fit", label: "Best fit" },
  { value: "hiring_first", label: "Hiring first" },
  { value: "final_score", label: "Deskie Score" },
  { value: "review_count", label: "Reviews" },
  { value: "rating", label: "Rating" },
];

const FIT_RANK: Record<string, number> = { good: 2, borderline: 1, excluded: 0 };

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
  const [sortBy, setSortBy] = useState("best_fit");
  const [cityFilter, setCityFilter] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [demoFilter, setDemoFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [icpFilter, setIcpFilter] = useState("");

  // Bulk PoC research
  const [pocBulkLoading, setPocBulkLoading] = useState(false);
  const [pocBulkMsg, setPocBulkMsg] = useState<string | null>(null);

  const loadBusinesses = useCallback(async () => {
    setLoading(true);
    try {
      // Page through everything (500/page) so client-side filters always see
      // the full dataset — 2000 leads is 4 requests.
      const first = await api.listBusinesses({ sort_by: "final_score", limit: 500 });
      let all = first.businesses;
      while (all.length < first.total) {
        const page = await api.listBusinesses({
          sort_by: "final_score",
          limit: 500,
          offset: all.length,
        });
        if (!page.businesses.length) break;
        all = all.concat(page.businesses);
      }
      setBusinesses(all);
      setTotal(first.total);
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
      if (sourceFilter && b.discovery !== sourceFilter) return false;
      if (icpFilter && b.icp_fit !== icpFilter) return false;
      return true;
    });
    const byScore = (a: Business, b: Business) =>
      (b.score?.final_score ?? -1) - (a.score?.final_score ?? -1);
    const byHiring = (a: Business, b: Business) =>
      (b.discovery === "hiring" ? 1 : 0) - (a.discovery === "hiring" ? 1 : 0);
    return filtered.sort((a, b) => {
      if (sortBy === "best_fit") {
        const fitDiff = (FIT_RANK[b.icp_fit] ?? 2) - (FIT_RANK[a.icp_fit] ?? 2);
        if (fitDiff !== 0) return fitDiff;
        const h = byHiring(a, b);
        if (h !== 0) return h;
        return byScore(a, b);
      }
      if (sortBy === "hiring_first") {
        const h = byHiring(a, b);
        if (h !== 0) return h;
        return byScore(a, b);
      }
      if (sortBy === "rating") return (b.rating ?? -1) - (a.rating ?? -1);
      if (sortBy === "review_count") return (b.review_count ?? -1) - (a.review_count ?? -1);
      return byScore(a, b);
    });
  }, [businesses, search, cityFilter, countryFilter, categoryFilter, priority, demoFilter, sourceFilter, icpFilter, sortBy]);

  const filtersActive = !!(search || cityFilter || countryFilter || categoryFilter || priority || demoFilter || sourceFilter || icpFilter);
  const clearFilters = () => {
    setSearch(""); setCityFilter(""); setCountryFilter("");
    setCategoryFilter(""); setPriority(""); setDemoFilter("");
    setSourceFilter(""); setIcpFilter("");
  };

  // Rendering thousands of heavy rows at once janks the page — reveal in
  // slabs of 200. Reset whenever the filtered set changes.
  const [visibleCount, setVisibleCount] = useState(200);
  useEffect(() => {
    setVisibleCount(200);
  }, [search, cityFilter, countryFilter, categoryFilter, priority, demoFilter, sourceFilter, icpFilter, sortBy]);
  const visible = displayed.slice(0, visibleCount);

  // ── Background job transparency ─────────────────────────────────────────
  // Research jobs run in the background; without this the only feedback lived
  // inside the (closeable) form — a failed run just "vanished". Poll the job
  // status and keep a banner on the dashboard: spinner + live progress while
  // running, and a persistent success/error summary once finished.
  type JobState = {
    status: string; total_pairs?: number; pairs_done?: number;
    leads_found?: number; current?: string | null; errors?: string[];
    finished_at?: string;
  };
  const [job, setJob] = useState<JobState | null>(null);
  const [dismissedJob, setDismissedJob] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const s = (await api.bulkStatus()) as JobState;
        if (!stopped) setJob(s);
      } catch { /* backend briefly unreachable — keep polling */ }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => { stopped = true; clearInterval(id); };
  }, []);
  // Refresh the table as background leads land / when the job finishes.
  useEffect(() => {
    if (job?.status === "running" || job?.status === "completed") loadBusinesses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, job?.leads_found]);

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

        {/* Background research job status — always visible, can't "vanish" */}
        {job?.status === "running" && (
          <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-xl px-4 py-3 text-sm text-indigo-200 flex items-center gap-3">
            <span className="animate-spin text-lg">⟳</span>
            <div>
              <p className="font-medium">
                Research job running{job.current ? ` — ${job.current}` : ""}
              </p>
              <p className="text-xs text-indigo-300/80 mt-0.5">
                {job.pairs_done ?? 0}/{job.total_pairs ?? "?"} searches done · {job.leads_found ?? 0} leads so far — new leads appear below as they land
              </p>
            </div>
          </div>
        )}
        {job?.status === "completed" && job.finished_at && dismissedJob !== job.finished_at && (
          <div
            className={`border rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3 ${
              job.errors?.length
                ? "bg-red-500/10 border-red-500/30 text-red-300"
                : "bg-green-500/10 border-green-500/30 text-green-300"
            }`}
          >
            <div>
              <p className="font-medium">
                {job.errors?.length
                  ? "⚠️ Last research job finished with problems"
                  : "✅ Last research job completed"}
                {" — "}{job.leads_found ?? 0} leads found
              </p>
              {(job.errors || []).map((e, i) => (
                <p key={i} className="text-xs mt-1 opacity-90">{e}</p>
              ))}
            </div>
            <button
              onClick={() => setDismissedJob(job.finished_at!)}
              className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        )}

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
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">Found Via: Any</option>
            <option value="hiring" className="bg-slate-900">🎯 Hiring-first</option>
            <option value="industry" className="bg-slate-900">🏢 Industry search</option>
          </select>

          <select
            value={icpFilter}
            onChange={(e) => setIcpFilter(e.target.value)}
            className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" className="bg-slate-900">Fit: Any</option>
            <option value="good" className="bg-slate-900">✅ Good fit</option>
            <option value="borderline" className="bg-slate-900">⚠️ Borderline</option>
            <option value="excluded" className="bg-slate-900">🚫 Poor fit</option>
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
            title="Find decision makers with VERIFIED work emails via Apollo (SerpAPI web search as fallback) for leads that don't have them yet. Spends Apollo email credits."
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
            {(filtersActive || displayed.length > visibleCount) && (
              <p className="text-xs text-slate-400 -mt-2">
                Showing {Math.min(visibleCount, displayed.length)} of {displayed.length}
                {filtersActive ? ` filtered (${businesses.length} total)` : " leads"}
              </p>
            )}
            <LeadTable businesses={visible} />
            {displayed.length > visibleCount && (
              <div className="text-center">
                <button
                  onClick={() => setVisibleCount((c) => c + 200)}
                  className="px-4 py-2 text-sm text-indigo-300 hover:text-indigo-200 border border-indigo-500/40 rounded-lg transition-colors"
                >
                  Show 200 more ({displayed.length - visibleCount} remaining)
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

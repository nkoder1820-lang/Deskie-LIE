"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Business } from "@/lib/api";
import { ScoreRing, BreakdownCard } from "@/components/ScoreCard";

const PRIORITY_STYLES: Record<string, string> = {
  HOT: "bg-red-500/20 text-red-400 border border-red-500/40",
  HIGH: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
  LOW: "bg-slate-500/20 text-slate-400 border border-slate-500/40",
};

const PITCH_ANGLE_STYLES: Record<string, string> = {
  "🔥 Missed Calls": "bg-red-500/20 text-red-400 border-red-500/40",
  "💰 Wasting Ad Budget": "bg-green-500/20 text-green-400 border-green-500/40",
  "💼 Hiring Receptionist": "bg-blue-500/20 text-blue-400 border-blue-500/40",
  "🌙 After-Hours Leak": "bg-purple-500/20 text-purple-400 border-purple-500/40",
  "🌐 No Website": "bg-slate-500/20 text-slate-400 border-slate-500/40",
  "📅 No Booking System": "bg-gray-500/20 text-gray-400 border-gray-500/40",
  "✨ General AI Upgrade": "bg-indigo-500/20 text-indigo-400 border-indigo-500/40",
};

export default function LeadDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [business, setBusiness] = useState<Business | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.id) {
      api.getBusiness(params.id as string)
        .then(setBusiness)
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [params.id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex items-center justify-center text-slate-400">
        <span className="animate-spin text-2xl mr-3">⟳</span> Loading lead...
      </div>
    );
  }

  if (!business) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex flex-col items-center justify-center text-slate-400">
        <p className="text-2xl mb-4">🔍</p>
        <p>Business not found.</p>
        <button onClick={() => router.push("/")} className="mt-4 text-indigo-400 hover:text-indigo-300 text-sm">
          ← Back to Dashboard
        </button>
      </div>
    );
  }

  const score = business.score;
  const report = business.report;
  const priority = score?.priority;
  const hours = business.opening_hours?.weekday_text as string[] | undefined;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      {/* Header */}
      <header className="border-b border-white/10 bg-white/5 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => router.push("/")}
            className="text-slate-400 hover:text-white transition-colors text-sm"
          >
            ← Dashboard
          </button>
          <div className="w-px h-4 bg-white/20" />
          <h1 className="font-semibold text-sm text-white truncate">{business.name}</h1>
          {priority && (
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${PRIORITY_STYLES[priority]}`}>
              {priority}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Hero */}
        <div className="bg-gradient-to-br from-indigo-900/30 to-slate-900/50 border border-white/10 rounded-2xl p-6">
          <div className="flex flex-col md:flex-row md:items-start gap-6">
            {/* Score Ring */}
            <div className="flex-shrink-0 flex flex-col items-center gap-2 bg-white/5 rounded-xl p-6 min-w-[140px]">
              <p className="text-xs text-slate-400 uppercase tracking-wide font-medium">Deskie Score</p>
              <div className="relative flex items-center justify-center" style={{ width: 130, height: 130 }}>
                <svg width="130" height="130" className="-rotate-90">
                  <circle cx="65" cy="65" r="52" fill="none" stroke="#1e293b" strokeWidth="10" />
                  <circle
                    cx="65" cy="65" r="52"
                    fill="none"
                    stroke={
                      (score?.final_score ?? 0) >= 90 ? "#f87171" :
                      (score?.final_score ?? 0) >= 75 ? "#fb923c" :
                      (score?.final_score ?? 0) >= 50 ? "#facc15" : "#64748b"
                    }
                    strokeWidth="10"
                    strokeDasharray={`${((score?.final_score ?? 0) / 100) * (2 * Math.PI * 52)} ${2 * Math.PI * 52}`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute text-center">
                  <p className="text-4xl font-bold text-white leading-none">
                    {score?.final_score != null ? score.final_score.toFixed(0) : "—"}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">/ 100</p>
                </div>
              </div>
              {priority && (
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${PRIORITY_STYLES[priority]}`}>
                  {priority}
                </span>
              )}
              {score?.pitch_angle && (
                <div className={`mt-1 px-2.5 py-1 rounded-md border text-xs text-center font-semibold ${PITCH_ANGLE_STYLES[score.pitch_angle] || "bg-white/10 text-white"}`}>
                  {score.pitch_angle}
                </div>
              )}
            </div>

            {/* Business Info */}
            <div className="flex-1 space-y-3">
              <div>
                <h2 className="text-2xl font-bold text-white">{business.name}</h2>
                <p className="text-slate-400 text-sm mt-0.5 capitalize">
                  {business.category.replace(/_/g, " ")} · {business.city}
                </p>
              </div>

              <div className="flex flex-wrap gap-3 text-sm">
                {business.phone && (
                  <span className="flex items-center gap-1.5 text-slate-300">
                    <span>📞</span> {business.phone}
                  </span>
                )}
                {business.rating != null && (
                  <span className="flex items-center gap-1.5 text-slate-300">
                    <span>⭐</span> {business.rating} ({business.review_count?.toLocaleString()} reviews)
                  </span>
                )}
                {business.website && (
                  <a
                    href={business.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    <span>🌐</span> Website ↗
                  </a>
                )}
              </div>

              {business.address && (
                <p className="text-sm text-slate-400">📍 {business.address}</p>
              )}

              {/* Qualification Reason */}
              {score?.qualification_reason && (
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 mt-2">
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-1.5">
                    🎯 Qualification Reason
                  </p>
                  <p className="text-slate-200 text-sm">{score.qualification_reason}</p>
                </div>
              )}

              {/* Recommended Pitch */}
              {report?.recommended_pitch && (
                <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-xl p-4 mt-2">
                  <p className="text-xs text-indigo-400 uppercase tracking-wide font-medium mb-1.5">
                    💬 Recommended Pitch
                  </p>
                  <p className="text-white text-sm italic">"{report.recommended_pitch}"</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Score Breakdown */}
        <section>
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Score Breakdown
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <BreakdownCard
              label="Pain Score"
              score={score?.pain_score ?? null}
              breakdown={score?.pain_breakdown ?? null}
              weight="40%"
            />
            <BreakdownCard
              label="Business Value"
              score={score?.business_value_score ?? null}
              breakdown={score?.value_breakdown ?? null}
              weight="25%"
            />
            <BreakdownCard
              label="Digital Adoption"
              score={score?.digital_score ?? null}
              breakdown={score?.digital_breakdown ?? null}
              weight="20%"
            />
            <BreakdownCard
              label="Buying Timing"
              score={score?.timing_score ?? null}
              breakdown={score?.timing_breakdown ?? null}
              weight="15%"
            />
          </div>
        </section>

        {/* Report */}
        {report && (
          <section>
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
              Lead Intelligence Report
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {report.summary && (
                <div className="md:col-span-3 bg-white/5 border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">Summary</p>
                  <p className="text-sm text-slate-200 leading-relaxed">{report.summary}</p>
                </div>
              )}

              {report.top_reasons && report.top_reasons.length > 0 && (
                <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-green-400 uppercase tracking-wide font-medium mb-2">Top Reasons</p>
                  <ul className="space-y-1.5">
                    {report.top_reasons.map((r, i) => (
                      <li key={i} className="text-xs text-slate-300 flex gap-1.5">
                        <span className="text-green-400 shrink-0">✓</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {report.pain_points && report.pain_points.length > 0 && (
                <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-red-400 uppercase tracking-wide font-medium mb-2">Pain Points</p>
                  <ul className="space-y-1.5">
                    {report.pain_points.map((p, i) => (
                      <li key={i} className="text-xs text-slate-300 flex gap-1.5">
                        <span className="text-red-400 shrink-0">!</span> {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Opening Hours */}
        {hours && hours.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
              Operating Hours
            </h3>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {hours.map((h, i) => {
                const [day, ...rest] = h.split(":");
                const isLate = h.includes("PM") && (h.includes("9:") || h.includes("10:") || h.includes("11:"));
                return (
                  <div key={i} className="flex items-center justify-between text-sm py-0.5">
                    <span className="text-slate-400 w-28">{day}</span>
                    <span className={`${isLate ? "text-orange-400" : "text-slate-300"}`}>
                      {rest.join(":").trim()}
                      {isLate && " 🔥"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

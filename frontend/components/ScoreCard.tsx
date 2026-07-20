"use client";

import { ScoreBreakdown } from "@/lib/api";

interface ScoreRingProps {
  score: number | null;
  label: string;
  size?: "sm" | "lg";
}

export function ScoreRing({ score, label, size = "sm" }: ScoreRingProps) {
  const s = score ?? 0;
  const radius = size === "lg" ? 52 : 28;
  const stroke = size === "lg" ? 7 : 5;
  const circumference = 2 * Math.PI * radius;
  const progress = (s / 100) * circumference;
  const dim = (radius + stroke) * 2;

  const color =
    s >= 90 ? "#f87171" : s >= 75 ? "#fb923c" : s >= 50 ? "#facc15" : "#64748b";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={dim} height={dim} className="-rotate-90">
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={radius}
          fill="none"
          stroke="#1e293b"
          strokeWidth={stroke}
        />
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${progress} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <div className="text-center -mt-1" style={{ marginTop: size === "lg" ? `-${dim * 0.6}px` : `-${dim * 0.55}px` }}>
        <div
          className="font-bold tabular-nums"
          style={{
            fontSize: size === "lg" ? "2rem" : "0.9rem",
            color,
            lineHeight: 1,
          }}
        >
          {score != null ? score.toFixed(0) : "—"}
        </div>
      </div>
      <p className="text-xs text-slate-400 text-center mt-1 leading-tight">{label}</p>
    </div>
  );
}

const SUB_SCORE_LABELS: Record<string, string> = {
  // Pain
  phone_dependency: "Phone Dependency",
  no_booking_automation: "No Booking Automation",
  negative_call_reviews: "Negative Call Reviews",
  receptionist_hiring: "Hiring Front Desk",
  extended_hours: "Extended Hours",
  after_hours_leak: "After-Hours Leak",
  
  // Value
  industry_value: "Industry Value Tier",
  location_tier: "Location Tier",
  review_volume: "Review Volume",
  customer_value: "Avg Client Value",
  business_size: "Business Size Proxy",
  
  // Digital
  has_website: "Has Website",
  runs_ads: "Runs Ads (Google/Meta)",
  social_activity: "Social Activity",
  existing_software: "CRM/Booking Tech Detected",
  online_presence: "Website Quality",
  
  // Timing
  is_hiring: "Actively Hiring",
  expanding: "Expansion Signal",
  marketing_activity: "Marketing Activity",
  recent_growth: "Recent Growth",
};

interface BreakdownCardProps {
  label: string;
  score: number | null;
  breakdown: ScoreBreakdown | null;
  weight: string;
}

export function BreakdownCard({ label, score, breakdown, weight }: BreakdownCardProps) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide font-medium">{label}</p>
          <p className="text-xs text-slate-600 mt-0.5">Weight: {weight}</p>
        </div>
        <span className="text-2xl font-bold text-white">
          {score != null ? score.toFixed(0) : "—"}
        </span>
      </div>

      {/* Score bar */}
      <div className="w-full h-1.5 bg-white/10 rounded-full mb-4">
        <div
          className="h-full rounded-full bg-indigo-500 transition-all duration-700"
          style={{ width: `${score ?? 0}%` }}
        />
      </div>

      {/* Sub-scores (Signals Breakdown) */}
      {breakdown?.sub_scores && Object.keys(breakdown.sub_scores).length > 0 && (
        <div className="mb-4 space-y-2 border-t border-white/5 pt-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2">Signals Breakdown</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {Object.entries(breakdown.sub_scores).map(([key, val]) => {
              const signalLabel = SUB_SCORE_LABELS[key] || key.replace(/_/g, " ");
              const displayVal = typeof val === "number" ? Math.round(val * 100) : 0;
              return (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 truncate pr-2" title={signalLabel}>{signalLabel}</span>
                  <span className={`font-mono font-medium ${displayVal > 70 ? "text-indigo-400" : displayVal > 30 ? "text-slate-300" : "text-slate-500"}`}>
                    {displayVal}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Evidence */}
      {breakdown?.evidence && breakdown.evidence.length > 0 && (
        <div className="border-t border-white/5 pt-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2">Key Evidence</p>
          <ul className="space-y-1">
            {breakdown.evidence.slice(0, 3).map((e, i) => (
              <li key={i} className="text-xs text-slate-400 flex gap-1.5">
                <span className="text-indigo-400 mt-0.5 shrink-0">✓</span>
                <span className="flex-1">
                  {e.text}
                  {e.source_url && (
                    <a
                      href={e.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={e.source_label || "Verify this"}
                      onClick={(ev) => ev.stopPropagation()}
                      className="text-indigo-400 hover:text-indigo-300 ml-1"
                    >
                      🔗
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

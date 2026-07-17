const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Business {
  id: string;
  name: string;
  category: string;
  city: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  address: string | null;
  rating: number | null;
  review_count: number | null;
  opening_hours: Record<string, unknown> | null;
  social_links: Record<string, string>;
  detected_tech: string[];
  source: string;
  created_at: string | null;
  score: LeadScore | null;
  report: LeadReport | null;
  research?: Record<string, unknown>;
}

export interface LeadScore {
  final_score: number | null;
  priority: "HOT" | "HIGH" | "MEDIUM" | "LOW" | null;
  pitch_angle: string | null;
  qualification_reason: string | null;
  pain_score: number | null;
  business_value_score: number | null;
  digital_score: number | null;
  timing_score: number | null;
  pain_breakdown: ScoreBreakdown | null;
  value_breakdown: ScoreBreakdown | null;
  digital_breakdown: ScoreBreakdown | null;
  timing_breakdown: ScoreBreakdown | null;
}

export interface ScoreBreakdown {
  score: number;
  sub_scores: Record<string, number>;
  evidence: string[];
}

export interface LeadReport {
  summary: string | null;
  top_reasons: string[] | null;
  pain_points: string[] | null;
  recommended_pitch: string | null;
}

export interface ResearchRequest {
  industry: string;
  city: string;
  max_results: number;
}

export interface BusinessListResponse {
  total: number;
  offset: number;
  limit: number;
  businesses: Business[];
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Research
  runResearch: (req: ResearchRequest) =>
    apiFetch<{ status: string; message: string; leads_count: number }>(
      "/api/research/run",
      { method: "POST", body: JSON.stringify(req) }
    ),

  listIndustries: () =>
    apiFetch<{ industries: { key: string; label: string }[] }>(
      "/api/research/industries"
    ),

  // Businesses
  listBusinesses: (params: {
    city?: string;
    category?: string;
    priority?: string;
    sort_by?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params.city) qs.set("city", params.city);
    if (params.category) qs.set("category", params.category);
    if (params.priority) qs.set("priority", params.priority);
    if (params.sort_by) qs.set("sort_by", params.sort_by);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    return apiFetch<BusinessListResponse>(`/api/businesses?${qs}`);
  },

  getBusiness: (id: string) =>
    apiFetch<Business>(`/api/businesses/${id}`),
};

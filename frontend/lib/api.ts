const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Business {
  id: string;
  name: string;
  category: string;
  city: string;
  phone: string | null;
  email: string | null;
  emails: string[];
  phones: string[];
  whatsapp: string | null;
  whatsapp_link: string | null;
  decision_makers: { name: string; title: string }[];
  poc_contacts: PocContact[];
  poc_researched_at: string | null;
  linkedin_search: string;
  website: string | null;
  maps_url: string | null;
  contact_form_url: string | null;
  address: string | null;
  rating: number | null;
  review_count: number | null;
  opening_hours: Record<string, unknown> | null;
  social_links: Record<string, string>;
  detected_tech: string[];
  source: string;
  demo_slug: string | null;
  demo_url: string | null;
  demo_created_at: string | null;
  created_at: string | null;
  score: LeadScore | null;
  report: LeadReport | null;
  research?: Record<string, unknown>;
}

export interface EvidenceSource {
  label: string;
  url: string;
}

export interface LeadScore {
  final_score: number | null;
  priority: "HOT" | "HIGH" | "MEDIUM" | "LOW" | null;
  pitch_angle: string | null;
  qualification_reason: string | null;
  pitch_source: EvidenceSource | null;
  pain_score: number | null;
  business_value_score: number | null;
  digital_score: number | null;
  timing_score: number | null;
  pain_breakdown: ScoreBreakdown | null;
  value_breakdown: ScoreBreakdown | null;
  digital_breakdown: ScoreBreakdown | null;
  timing_breakdown: ScoreBreakdown | null;
}

export interface PocContact {
  name: string;
  title: string;
  emails: string[];
  guessed_emails: string[];
  phones: string[];
  linkedin_url: string | null;
  confidence: "verified_on_site" | "public_search" | "inferred";
  source: string;
}

export interface PocOutreach {
  name: string;
  title: string;
  email_subject: string;
  email_body: string;
  whatsapp_message: string;
}

export interface EvidenceItem {
  text: string;
  source_url: string | null;
  source_label: string | null;
}

export interface ScoreBreakdown {
  score: number;
  sub_scores: Record<string, number>;
  evidence: EvidenceItem[];
}

export interface LeadReport {
  summary: string | null;
  top_reasons: string[] | null;
  pain_points: string[] | null;
  recommended_pitch: string | null;
  outreach_subject: string | null;
  outreach_email: string | null;
  whatsapp_message: string | null;
  email_sent_at: string | null;
  poc_outreach: PocOutreach[];
  sources: EvidenceSource[];
}

export interface ResearchRequest {
  industry: string;
  city: string;
  country?: string;
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

  // Bulk research
  runBulkResearch: (req: {
    industries: string[];
    cities: string[];
    country?: string;
    max_results_per_pair?: number;
  }) =>
    apiFetch<{ status: string; pairs: number; max_leads: number }>(
      "/api/research/bulk",
      { method: "POST", body: JSON.stringify(req) }
    ),

  bulkStatus: () =>
    apiFetch<{
      status: string;
      total_pairs?: number;
      pairs_done?: number;
      leads_found?: number;
      current?: string | null;
      errors?: string[];
    }>("/api/research/bulk/status"),

  // Outreach sending
  outreachConfig: () =>
    apiFetch<{ email_sending_enabled: boolean; from_email: string | null }>(
      "/api/outreach/config"
    ),

  sendEmail: (businessId: string, overrides?: { to?: string; subject?: string; body?: string }) =>
    apiFetch<{ status: string; to: string; email_id: string }>(
      `/api/outreach/send-email/${businessId}`,
      { method: "POST", body: JSON.stringify(overrides || {}) }
    ),

  // Decision-maker (PoC) research
  researchPoc: (businessId: string) =>
    apiFetch<{ poc_contacts: PocContact[]; poc_outreach: PocOutreach[]; serpapi_used: boolean }>(
      `/api/research/poc/${businessId}`,
      { method: "POST" }
    ),

  researchPocBulk: (businessIds?: string[], limit?: number) =>
    apiFetch<{ status: string; targeted: number; succeeded: number }>(
      "/api/research/poc/bulk",
      { method: "POST", body: JSON.stringify({ business_ids: businessIds, limit: limit ?? 20 }) }
    ),
};

// ── Email + WhatsApp link builders ──────────────────────────────────────────
//
// mailto: and sms: rely on the OS having a default handler registered —
// on a fresh Windows machine (no Outlook set as default) that's usually
// nobody, so clicking them just does nothing with no visible error. Gmail's
// own compose URL is a plain https link (always opens), and Gmail
// autosaves any open compose window as a draft within a couple of seconds —
// so opening it IS "saving a draft, ready to send" with zero OAuth setup.
//
// Deliberately NOT passing fs=1 (force full-screen compose): that skips
// loading the normal Gmail shell entirely, landing on a bare editor with
// no inbox chrome and no visible account indicator — confusing, and no way
// to tell which Google account it's about to send from. Without it, the
// link opens as the ordinary compose popup docked inside your actual
// Gmail inbox, where the account avatar is visible as usual. There's no
// way for a plain link like this to force a specific Google account if
// you're signed into more than one — Gmail uses whichever is currently
// active in that browser tab.
export function gmailComposeLink(to: string, subject: string, body: string): string {
  const params = new URLSearchParams({ view: "cm", to, su: subject, body });
  return `https://mail.google.com/mail/?${params.toString()}`;
}

function whatsappDigits(phone: string): string {
  return phone.replace(/[^\d+]/g, "").replace(/^\+/, "");
}

// ── Prefilled outreach links for a specific decision maker (PoC) ────────────
export function pocOutreachLinks(
  poc: PocContact,
  draft: PocOutreach | undefined,
  business: Business
): Record<string, string> {
  const links: Record<string, string> = {};
  const email = poc.emails[0] || poc.guessed_emails[0];
  const subject = draft?.email_subject || "";
  const body = draft?.email_body || "";
  const waMsg = draft?.whatsapp_message || "";

  if (email) {
    links.email = gmailComposeLink(email, subject, body);
    links.emailFallback = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
  // Fall back through PoC's own number → business WhatsApp → main business
  // phone, so a WhatsApp option shows up for nearly every lead, not only
  // the ones where we specifically detected a "WhatsApp Business" badge.
  const phone = poc.phones[0] || business.whatsapp || business.phone;
  if (phone) {
    const digits = whatsappDigits(phone);
    links.whatsapp = `https://wa.me/${digits}?text=${encodeURIComponent(waMsg)}`;
    links.sms = `sms:${phone.replace(/[^\d+]/g, "")}?&body=${encodeURIComponent(waMsg)}`;
  }
  if (poc.linkedin_url) {
    links.linkedin = poc.linkedin_url;
  }
  return links;
}

// ── Prefilled outreach links per platform ────────────────────────────────────
// Every platform that supports prefilled text gets a ready-to-fire link.
// (Instagram/LinkedIn DMs don't support prefill — we link to the profile.)
export function outreachLinks(b: Business): Record<string, string> {
  const links: Record<string, string> = {};
  const subject = b.report?.outreach_subject || "";
  const body = b.report?.outreach_email || "";
  const waMsg = b.report?.whatsapp_message || "";

  if (b.email) {
    links.email = gmailComposeLink(b.email, subject, body);
    links.emailFallback = `mailto:${b.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
  const waNumber = b.whatsapp || b.phone;
  if (waNumber) {
    const digits = whatsappDigits(waNumber);
    links.whatsapp = `https://wa.me/${digits}?text=${encodeURIComponent(waMsg)}`;
  }
  if (b.phone) {
    links.sms = `sms:${b.phone.replace(/[^\d+]/g, "")}?&body=${encodeURIComponent(waMsg)}`;
  }
  const fb = b.social_links?.facebook;
  if (fb) {
    const slug = fb.replace(/^https?:\/\/(www\.)?(facebook|fb)\.com\//i, "").split(/[/?]/)[0];
    if (slug && !/^\d+$/.test(slug) && slug !== "people") {
      links.messenger = `https://m.me/${slug}`;
    }
  }
  return links;
}

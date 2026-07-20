"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Business, outreachLinks, pocOutreachLinks, PocContact } from "@/lib/api";
import { ScoreRing, BreakdownCard } from "@/components/ScoreCard";
import { channelLinks } from "@/components/LeadTable";

const CONFIDENCE_STYLES: Record<string, { label: string; className: string }> = {
  verified_on_site: { label: "From their website", className: "bg-blue-500/15 text-blue-300 border-blue-500/30" },
  public_search: { label: "Found via web search", className: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  inferred: { label: "Guessed — unverified", className: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
};

const PRIORITY_STYLES: Record<string, string> = {
  HOT: "bg-red-500/20 text-red-400 border border-red-500/40",
  HIGH: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
  MEDIUM: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40",
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
  const [sendingEnabled, setSendingEnabled] = useState(false);
  const [sendState, setSendState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [sendMsg, setSendMsg] = useState<string | null>(null);
  const [pocLoading, setPocLoading] = useState(false);
  const [pocError, setPocError] = useState<string | null>(null);
  const [pocSendState, setPocSendState] = useState<Record<string, "sending" | "sent" | "error">>({});
  const [pocSendMsg, setPocSendMsg] = useState<Record<string, string>>({});

  useEffect(() => {
    if (params.id) {
      api.getBusiness(params.id as string)
        .then(setBusiness)
        .catch(console.error)
        .finally(() => setLoading(false));
    }
    api.outreachConfig()
      .then((c) => setSendingEnabled(c.email_sending_enabled))
      .catch(() => setSendingEnabled(false));
  }, [params.id]);

  const handleSendEmail = async () => {
    if (!business?.email) return;
    if (!window.confirm(`Send the cold email to ${business.email} now?`)) return;
    setSendState("sending");
    setSendMsg(null);
    try {
      const r = await api.sendEmail(business.id);
      setSendState("sent");
      setSendMsg(`Sent to ${r.to}`);
    } catch (e) {
      setSendState("error");
      setSendMsg(e instanceof Error ? e.message : "Send failed");
    }
  };

  const handleResearchPoc = async () => {
    if (!business) return;
    setPocLoading(true);
    setPocError(null);
    try {
      const r = await api.researchPoc(business.id);
      setBusiness({
        ...business,
        poc_contacts: r.poc_contacts,
        poc_researched_at: new Date().toISOString(),
        report: business.report ? { ...business.report, poc_outreach: r.poc_outreach } : business.report,
      });
    } catch (e) {
      setPocError(e instanceof Error ? e.message : "PoC research failed");
    } finally {
      setPocLoading(false);
    }
  };

  const handleSendPocEmail = async (poc: PocContact, draft: { email_subject: string; email_body: string } | undefined) => {
    const email = poc.emails[0] || poc.guessed_emails[0];
    if (!email || !business) return;
    if (!window.confirm(`Send the cold email to ${poc.name} <${email}> now?`)) return;
    setPocSendState((s) => ({ ...s, [poc.name]: "sending" }));
    try {
      const r = await api.sendEmail(business.id, {
        to: email,
        subject: draft?.email_subject,
        body: draft?.email_body,
      });
      setPocSendState((s) => ({ ...s, [poc.name]: "sent" }));
      setPocSendMsg((s) => ({ ...s, [poc.name]: `Sent to ${r.to}` }));
    } catch (e) {
      setPocSendState((s) => ({ ...s, [poc.name]: "error" }));
      setPocSendMsg((s) => ({ ...s, [poc.name]: e instanceof Error ? e.message : "Send failed" }));
    }
  };

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
  const links = channelLinks(business);
  const send = outreachLinks(business);
  // Primary: Gmail's own compose URL — a plain https link that always
  // opens, and Gmail autosaves the open compose window as a draft within
  // seconds, so this is "saved to Gmail drafts, ready to send" with no
  // OAuth setup. Fallback: mailto, for people who don't use Gmail.
  const emailDraft = send.email || null;
  const emailFallback = send.emailFallback || (business.email ? `mailto:${business.email}` : null);

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
              {score?.pitch_source && (
                <a
                  href={score.pitch_source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={score.pitch_source.label}
                  className="text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  🔗 Verify source
                </a>
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
                  {score.pitch_source && (
                    <a
                      href={score.pitch_source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors mt-2 inline-flex items-center gap-1"
                    >
                      🔗 {score.pitch_source.label} ↗
                    </a>
                  )}
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

        {/* Decision Makers — research trigger + channels_poc */}
        <section>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
              Decision Makers
            </h3>
            <button
              onClick={handleResearchPoc}
              disabled={pocLoading}
              title="Search the web + LinkedIn for who actually makes purchasing decisions here. Uses SerpAPI quota."
              className="text-xs px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 disabled:text-indigo-400 rounded-lg text-white font-medium transition-colors flex items-center gap-1.5"
            >
              {pocLoading ? (
                <>
                  <span className="animate-spin">⟳</span> Researching...
                </>
              ) : business.poc_researched_at ? (
                "🔎 Re-research decision makers"
              ) : (
                "🔎 Research decision makers"
              )}
            </button>
          </div>

          {pocError && <p className="text-xs text-red-400 mb-3">{pocError}</p>}
          {business.poc_researched_at && !pocError && (
            <p className="text-xs text-slate-500 mb-3">
              Last researched {new Date(business.poc_researched_at).toLocaleString()}
            </p>
          )}

          {business.poc_contacts.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {business.poc_contacts.map((poc) => {
                const pocLinks = pocOutreachLinks(poc, undefined, business);
                const conf = CONFIDENCE_STYLES[poc.confidence] || CONFIDENCE_STYLES.inferred;
                return (
                  <div key={poc.name} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm text-white font-medium">{poc.name}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{poc.title}</p>
                      </div>
                    </div>
                    <span className={`inline-block mt-2 px-2 py-0.5 rounded-full text-[10px] font-medium border ${conf.className}`}>
                      {conf.label}
                    </span>
                    <div className="flex items-center gap-2.5 mt-2.5 flex-wrap">
                      {(poc.emails[0] || poc.guessed_emails[0]) && (
                        <a
                          href={pocLinks.email}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={poc.emails[0] ? poc.emails[0] : `${poc.guessed_emails[0]} (guessed — verify before high-volume sending)`}
                          className="text-xs text-slate-300 hover:text-indigo-300 transition-colors"
                        >
                          ✉️ {poc.emails[0] ? "Email" : "Email (guess)"}
                        </a>
                      )}
                      {poc.phones[0] && (
                        <a href={`tel:${poc.phones[0]}`} className="text-xs text-slate-300 hover:text-emerald-300 transition-colors">
                          📞 Call
                        </a>
                      )}
                      {pocLinks.whatsapp && (
                        <a href={pocLinks.whatsapp} target="_blank" rel="noopener noreferrer" className="text-xs text-slate-300 hover:text-emerald-300 transition-colors">
                          💬 WhatsApp
                        </a>
                      )}
                      {poc.linkedin_url && (
                        <a href={poc.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-slate-300 hover:text-blue-300 transition-colors">
                          💼 LinkedIn
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {(business.decision_makers || []).map((d) => (
                <div key={d.name} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
                  <p className="text-sm text-white font-medium">{d.name}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{d.title}</p>
                </div>
              ))}
              <div className="bg-white/5 border border-dashed border-white/15 rounded-xl px-4 py-3">
                <p className="text-xs text-slate-400">
                  {business.decision_makers.length > 0
                    ? "Run research above to find contact details for these people."
                    : "No decision maker found yet — run the research above."}
                </p>
                <a
                  href={business.linkedin_search}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-indigo-400 hover:text-indigo-300 mt-1 inline-block"
                >
                  Search owner/manager on LinkedIn →
                </a>
              </div>
            </div>
          )}
        </section>

        {/* Decision-Maker Outreach Drafts (drafts_poc) */}
        {(report?.poc_outreach?.length || 0) > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
              Decision-Maker Outreach Drafts
            </h3>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {report!.poc_outreach.map((draft) => {
                const poc = business.poc_contacts.find((p) => p.name === draft.name);
                if (!poc) return null;
                const pocLinks = pocOutreachLinks(poc, draft, business);
                const email = poc.emails[0] || poc.guessed_emails[0];
                const state = pocSendState[poc.name];
                const msg = pocSendMsg[poc.name];
                return (
                  <OutreachCard
                    key={poc.name}
                    title={`✉️ ${draft.name} — ${draft.title || "Decision maker"}`}
                    subject={draft.email_subject}
                    body={draft.email_body}
                    actionLabel={pocLinks.email ? "📝 Draft in Gmail" : undefined}
                    actionHref={pocLinks.email}
                    extraAction={
                      <>
                        {pocLinks.emailFallback && (
                          <a
                            href={pocLinks.emailFallback}
                            title="Open with your default mail app instead"
                            className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-400 hover:text-white hover:border-white/30 transition-colors"
                          >
                            Other app
                          </a>
                        )}
                        {pocLinks.whatsapp && (
                          <a
                            href={pocLinks.whatsapp}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-300 hover:text-white hover:border-white/30 transition-colors"
                          >
                            💬 WhatsApp →
                          </a>
                        )}
                        {email && (
                          <button
                            onClick={() => handleSendPocEmail(poc, draft)}
                            disabled={!sendingEnabled || state === "sending" || state === "sent"}
                            title={
                              sendingEnabled
                                ? `Send via Resend to ${email}`
                                : "Set RESEND_API_KEY + OUTREACH_FROM_EMAIL in backend/.env to enable"
                            }
                            className="text-xs px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-400 rounded-md text-white transition-colors"
                          >
                            {state === "sending" ? "Sending..." : state === "sent" ? "✓ Sent" : "🚀 Send now"}
                          </button>
                        )}
                      </>
                    }
                    footer={
                      msg ? (
                        <p className={`text-xs mt-2 ${state === "error" ? "text-red-400" : "text-emerald-400"}`}>{msg}</p>
                      ) : !poc.emails[0] && poc.guessed_emails[0] ? (
                        <p className="text-xs mt-2 text-amber-400">
                          Email is a guess ({poc.guessed_emails[0]}) — verify before sending at volume.
                        </p>
                      ) : undefined
                    }
                  />
                );
              })}
            </div>
          </section>
        )}

        {/* Contact Channels */}
        <section>
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Reach Them Everywhere
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {business.email && (
              <ContactCard label="Email" value={business.email} href={emailDraft || emailFallback || undefined} copyValue={business.email} />
            )}
            {(business.emails || []).filter((e) => e !== business.email).map((e) => (
              <ContactCard key={e} label="Alt email" value={e} href={`mailto:${e}`} copyValue={e} />
            ))}
            {business.phone && (
              <ContactCard label="Phone" value={business.phone} href={`tel:${business.phone}`} copyValue={business.phone} />
            )}
            {(business.phones || []).filter((p) => p !== business.phone).map((p) => (
              <ContactCard key={p} label="Alt phone" value={p} href={`tel:${p}`} copyValue={p} />
            ))}
            {business.whatsapp && (
              <ContactCard label="WhatsApp" value={business.whatsapp} href={links.whatsapp} copyValue={business.whatsapp} />
            )}
            {business.website && (
              <ContactCard label="Website" value={business.website.replace(/^https?:\/\//, "")} href={business.website} copyValue={business.website} />
            )}
            {links.maps && <ContactCard label="Google Maps" value="Open listing ↗" href={links.maps} />}
            {business.contact_form_url && (
              <ContactCard label="Contact form" value="Open form ↗" href={business.contact_form_url} />
            )}
            {Object.entries(business.social_links || {})
              .filter(([k]) => !["google_maps", "whatsapp"].includes(k))
              .map(([k, v]) => (
                <ContactCard key={k} label={k} value={v.replace(/^https?:\/\//, "")} href={v} copyValue={v} />
              ))}
          </div>
        </section>

        {/* Ready-to-send Outreach */}
        {report && (report.outreach_email || report.whatsapp_message) && (
          <section>
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
              Ready-to-Send Outreach
            </h3>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {report.outreach_email && (
                <OutreachCard
                  title="✉️ Cold Email"
                  subject={report.outreach_subject}
                  body={report.outreach_email}
                  actionLabel={emailDraft ? "📝 Draft in Gmail" : undefined}
                  actionHref={emailDraft || undefined}
                  extraAction={
                    <>
                      {emailFallback && (
                        <a
                          href={emailFallback}
                          title="Open with your default mail app instead"
                          className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-400 hover:text-white hover:border-white/30 transition-colors"
                        >
                          Other app
                        </a>
                      )}
                      {business.email && (
                        <button
                          onClick={handleSendEmail}
                          disabled={!sendingEnabled || sendState === "sending" || sendState === "sent"}
                          title={
                            sendingEnabled
                              ? `Send via Resend to ${business.email}`
                              : "Set RESEND_API_KEY + OUTREACH_FROM_EMAIL in backend/.env to enable"
                          }
                          className="text-xs px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-400 rounded-md text-white transition-colors"
                        >
                          {sendState === "sending" ? "Sending..." :
                           sendState === "sent" ? "✓ Sent" :
                           report.email_sent_at ? "Send again" : "🚀 Send now"}
                        </button>
                      )}
                    </>
                  }
                  footer={
                    sendMsg ? (
                      <p className={`text-xs mt-2 ${sendState === "error" ? "text-red-400" : "text-emerald-400"}`}>
                        {sendMsg}
                      </p>
                    ) : report.email_sent_at ? (
                      <p className="text-xs mt-2 text-slate-500">
                        Last sent {new Date(report.email_sent_at).toLocaleString()}
                      </p>
                    ) : undefined
                  }
                />
              )}
              {report.whatsapp_message && (
                <OutreachCard
                  title="💬 WhatsApp / SMS"
                  body={report.whatsapp_message}
                  actionLabel={send.whatsapp ? "Open in WhatsApp" : undefined}
                  actionHref={send.whatsapp}
                  extraAction={
                    <>
                      {send.sms && (
                        <a
                          href={send.sms}
                          className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-300 hover:text-white hover:border-white/30 transition-colors"
                        >
                          SMS →
                        </a>
                      )}
                      {send.messenger && (
                        <a
                          href={send.messenger}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-300 hover:text-white hover:border-white/30 transition-colors"
                        >
                          Messenger →
                        </a>
                      )}
                    </>
                  }
                />
              )}
            </div>
          </section>
        )}

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

              {report.sources && report.sources.length > 0 && (
                <div className="md:col-span-3 bg-white/5 border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-indigo-400 uppercase tracking-wide font-medium mb-2">
                    🔗 Sources — click to verify
                  </p>
                  <ul className="space-y-1.5">
                    {report.sources.map((s, i) => (
                      <li key={i} className="text-xs flex gap-1.5">
                        <span className="text-indigo-400 shrink-0">↗</span>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-slate-300 hover:text-indigo-300 transition-colors truncate"
                          title={s.url}
                        >
                          {s.label}
                        </a>
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

// ── Contact + Outreach cards ────────────────────────────────────────────────

function ContactCard({
  label,
  value,
  href,
  copyValue,
}: {
  label: string;
  value: string;
  href?: string;
  copyValue?: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    if (!copyValue) return;
    navigator.clipboard.writeText(copyValue).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [copyValue]);

  const isExternal = href ? /^https?:/.test(href) : false;
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
        {href ? (
          <a
            href={href}
            target={isExternal ? "_blank" : undefined}
            rel={isExternal ? "noopener noreferrer" : undefined}
            className="text-sm text-slate-200 hover:text-indigo-300 transition-colors truncate block"
            title={value}
          >
            {value}
          </a>
        ) : (
          <p className="text-sm text-slate-200 truncate" title={value}>{value}</p>
        )}
      </div>
      {copyValue && (
        <button
          onClick={copy}
          title={`Copy ${label}`}
          className="shrink-0 text-xs text-slate-500 hover:text-indigo-400 transition-colors"
        >
          {copied ? "✓" : "⎘"}
        </button>
      )}
    </div>
  );
}

function OutreachCard({
  title,
  subject,
  body,
  actionLabel,
  actionHref,
  extraAction,
  footer,
}: {
  title: string;
  subject?: string | null;
  body: string;
  actionLabel?: string;
  actionHref?: string;
  extraAction?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    const full = subject ? `Subject: ${subject}\n\n${body}` : body;
    navigator.clipboard.writeText(full).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [subject, body]);

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-col">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <h4 className="text-sm font-semibold text-white">{title}</h4>
        <div className="flex items-center gap-2">
          <button
            onClick={copy}
            className="text-xs px-2.5 py-1 border border-white/15 rounded-md text-slate-300 hover:text-white hover:border-white/30 transition-colors"
          >
            {copied ? "✓ Copied" : "⎘ Copy"}
          </button>
          {actionLabel && actionHref && (
            <a
              href={actionHref}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 rounded-md text-white transition-colors"
            >
              {actionLabel} →
            </a>
          )}
          {extraAction}
        </div>
      </div>
      {subject && (
        <p className="text-xs text-slate-400 mb-2">
          <span className="text-slate-500">Subject:</span> {subject}
        </p>
      )}
      <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed flex-1">
        {body}
      </pre>
      {footer}
    </div>
  );
}

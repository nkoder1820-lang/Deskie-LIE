"use client";

import { Business, api } from "@/lib/api";
import Link from "next/link";
import { useState, useCallback, type MouseEvent } from "react";

interface Props {
  businesses: Business[];
  onPreviewEmail?: (b: Business) => void;
}

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

const SCORE_COLOR = (score: number | null) => {
  if (!score) return "text-slate-500";
  if (score >= 90) return "text-red-400";
  if (score >= 75) return "text-orange-400";
  if (score >= 50) return "text-yellow-400";
  return "text-slate-400";
};

export default function LeadTable({ businesses, onPreviewEmail }: Props) {
  if (businesses.length === 0) {
    return (
      <div className="text-center py-20 text-slate-500">
        <div className="text-5xl mb-4">🔍</div>
        <p className="text-lg">No leads found.</p>
        <p className="text-sm mt-1">Run a research job to discover businesses.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/10">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-slate-400 text-xs uppercase tracking-widest">
            {/* Contact + action columns lead, so the details you actually work
                from are visible without scrolling right. Classification
                (fit / found-via / pitch / reviews) trails behind them. */}
            <th className="text-left px-4 py-3 font-medium">Business</th>
            <th className="text-left px-4 py-3 font-medium">Email</th>
            <th className="text-left px-4 py-3 font-medium">Phone</th>
            <th className="text-left px-4 py-3 font-medium">Decision Maker</th>
            <th className="text-left px-4 py-3 font-medium">Outreach</th>
            <th className="text-left px-4 py-3 font-medium">Channels</th>
            <th className="text-left px-4 py-3 font-medium">Demo</th>
            <th className="text-center px-4 py-3 font-medium">Done</th>
            <th className="text-left px-4 py-3 font-medium">Notes</th>
            <th className="text-center px-4 py-3 font-medium">Quality</th>
            <th className="text-left px-4 py-3 font-medium hidden lg:table-cell">Fit</th>
            <th className="text-left px-4 py-3 font-medium hidden lg:table-cell">Found Via</th>
            <th className="text-left px-4 py-3 font-medium hidden xl:table-cell">Pitch Angle</th>
            <th className="text-right px-4 py-3 font-medium hidden xl:table-cell">Reviews</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {businesses.map((b) => {
            const score = b.score;
            const finalScore = score?.final_score;
            const priority = score?.priority;
            return (
              <tr
                key={b.id}
                className="hover:bg-white/5 transition-colors group"
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-white">{b.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5 capitalize">
                    {b.category.replace(/_/g, " ")} • {b.city}
                  </div>
                </td>
                <td className="px-4 py-3 max-w-[200px]">
                  <CopyCell value={b.email} placeholder="—" type="email" />
                </td>
                <td className="px-4 py-3">
                  <PhoneCell value={b.phone} />
                </td>
                <td className="px-4 py-3 max-w-[180px]">
                  <PocCell b={b} />
                </td>
                <td className="px-4 py-3">
                  <OutreachCell b={b} onPreviewEmail={onPreviewEmail} />
                </td>
                <td className="px-4 py-3">
                  <ChannelIcons b={b} />
                </td>
                <td className="px-4 py-3">
                  <DemoCell url={b.demo_url} />
                </td>
                <td className="px-4 py-3 text-center">
                  <ContactedCell b={b} />
                </td>
                <td className="px-4 py-3">
                  <NotesCell b={b} />
                </td>
                <td className="px-4 py-3 text-center">
                  <QualityCell b={b} />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  <FitCell fit={b.icp_fit} reasons={b.icp_reasons} />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  {b.discovery === "hiring" ? (
                    <span
                      className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/40 whitespace-nowrap"
                      title="Found via a live job posting — this business is actively hiring right now"
                    >
                      🎯 Hiring
                    </span>
                  ) : (
                    <span
                      className="px-2 py-0.5 rounded-md text-[11px] text-slate-400 border border-white/10 whitespace-nowrap"
                      title="Found via classic industry search"
                    >
                      🏢 Search
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 hidden xl:table-cell">
                  {score?.pitch_angle ? (
                    <span className="inline-flex items-center gap-1">
                      <span className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${PITCH_ANGLE_STYLES[score.pitch_angle] || "bg-white/10 text-white"}`}>
                        {score.pitch_angle}
                      </span>
                      {score.pitch_source && (
                        <a
                          href={score.pitch_source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={`Verify: ${score.pitch_source.label}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-indigo-400 hover:text-indigo-300 text-xs"
                        >
                          🔗
                        </a>
                      )}
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right hidden xl:table-cell text-slate-300">
                  {b.review_count != null ? b.review_count.toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {onPreviewEmail && (
                    <button
                      onClick={() => onPreviewEmail(b)}
                      title="Preview the outreach email for this lead"
                      className="mr-2 text-sm hover:scale-125 transition-transform"
                    >
                      ✉️
                    </button>
                  )}
                  <Link
                    href={`/leads/${b.id}`}
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-indigo-400 hover:text-indigo-300 text-xs font-medium"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Helper sub-components ────────────────────────────────────────────────────

const CHANNEL_META: { key: string; label: string; icon: string }[] = [
  { key: "website", label: "Website", icon: "🌐" },
  { key: "whatsapp", label: "WhatsApp", icon: "💬" },
  { key: "instagram", label: "Instagram", icon: "📸" },
  { key: "facebook", label: "Facebook", icon: "📘" },
  { key: "linkedin", label: "LinkedIn", icon: "💼" },
  { key: "twitter", label: "X / Twitter", icon: "🐦" },
  { key: "youtube", label: "YouTube", icon: "▶️" },
  { key: "tiktok", label: "TikTok", icon: "🎵" },
  { key: "yelp", label: "Yelp", icon: "⭐" },
  { key: "maps", label: "Google Maps", icon: "📍" },
  { key: "form", label: "Contact form", icon: "📝" },
];

export function channelLinks(b: Business): Record<string, string> {
  const links: Record<string, string> = {};
  if (b.website) links.website = b.website;
  // Fall back to the main business phone when no dedicated WhatsApp number
  // was detected — most SMB lines do have WhatsApp active, and wa.me just
  // no-ops harmlessly if not, so this only ever adds coverage.
  const waNumber = b.whatsapp || b.phone;
  if (waNumber) {
    const msg = b.report?.whatsapp_message;
    const digits = waNumber.replace(/[^\d+]/g, "").replace(/^\+/, "");
    links.whatsapp = msg
      ? `https://wa.me/${digits}?text=${encodeURIComponent(msg)}`
      : `https://wa.me/${digits}`;
  }
  const socials = b.social_links || {};
  for (const k of ["instagram", "facebook", "linkedin", "twitter", "youtube", "tiktok", "yelp"]) {
    if (socials[k]) links[k] = socials[k];
  }
  if (b.maps_url || socials.google_maps) links.maps = b.maps_url || socials.google_maps;
  if (b.contact_form_url) links.form = b.contact_form_url;
  return links;
}

function ChannelIcons({ b }: { b: Business }) {
  const links = channelLinks(b);
  const entries = CHANNEL_META.filter((c) => links[c.key]);
  if (entries.length === 0) {
    return <span className="text-slate-600 text-xs">—</span>;
  }
  return (
    <div className="flex items-center gap-1 flex-wrap max-w-[170px]">
      {entries.map((c) => (
        <a
          key={c.key}
          href={links[c.key]}
          target="_blank"
          rel="noopener noreferrer"
          title={c.label}
          onClick={(e) => e.stopPropagation()}
          className="text-sm leading-none hover:scale-125 transition-transform"
        >
          {c.icon}
        </a>
      ))}
    </div>
  );
}

function PocCell({ b }: { b: Business }) {
  const top = b.poc_contacts?.[0];
  if (!top) {
    return <span className="text-slate-600 text-xs">—</span>;
  }
  const isGuess = !top.emails[0] && !top.phones[0] && !!top.guessed_emails[0];
  const contact = top.emails[0] || top.phones[0] || top.guessed_emails[0];
  return (
    <div className="min-w-0">
      <p className="text-xs text-slate-200 truncate" title={`${top.name} — ${top.title}`}>
        {top.name}
      </p>
      <p className="text-[10px] text-slate-500 truncate">{top.title}</p>
      {contact && (
        <p className="text-[10px] text-slate-600 truncate" title={contact}>
          {contact}{isGuess ? " (guess)" : ""}
        </p>
      )}
    </div>
  );
}

function CopyCell({
  value,
  placeholder = "—",
  type = "text",
}: {
  value: string | null | undefined;
  placeholder?: string;
  type?: "email" | "text";
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [value]);

  if (!value) {
    return <span className="text-slate-600 text-xs">{placeholder}</span>;
  }

  return (
    <div className="flex items-center gap-1.5 group/copy max-w-full">
      <a
        href={`mailto:${value}`}
        className="text-xs text-slate-300 hover:text-indigo-300 transition-colors truncate"
        title={value}
        onClick={(e) => e.stopPropagation()}
      >
        {value}
      </a>
      <button
        onClick={handleCopy}
        title="Copy email"
        className="shrink-0 text-[10px] text-slate-600 hover:text-indigo-400 transition-colors"
      >
        {copied ? "✓" : "⎘"}
      </button>
    </div>
  );
}

const FIT_META: Record<string, { icon: string; label: string; cls: string }> = {
  good: { icon: "✅", label: "Good fit", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40" },
  borderline: { icon: "⚠️", label: "Borderline", cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/40" },
  excluded: { icon: "🚫", label: "Poor fit", cls: "bg-red-500/15 text-red-400 border-red-500/40" },
};

function FitCell({ fit, reasons }: { fit: Business["icp_fit"]; reasons: string[] }) {
  const m = FIT_META[fit] || FIT_META.good;
  return (
    <span
      className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border whitespace-nowrap cursor-help ${m.cls}`}
      title={(reasons || []).join("\n")}
    >
      {m.icon} {m.label}
    </span>
  );
}

const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-500/20 text-emerald-300 border-emerald-500/50",
  B: "bg-lime-500/15 text-lime-300 border-lime-500/40",
  C: "bg-yellow-500/15 text-yellow-300 border-yellow-500/40",
  D: "bg-slate-600/20 text-slate-400 border-slate-600/50",
};

/** One quality figure instead of the old score/priority/pain/value/digital
 * columns. Those sub-scores still exist and still drive this — they're just
 * internal now, shown only on hover for a sanity check. */
function QualityCell({ b }: { b: Business }) {
  const g = b.grade;
  if (!g) return <span className="text-slate-600">—</span>;
  const s = b.score;
  const detail = [
    `Deskie score ${s?.final_score?.toFixed(0) ?? "—"}`,
    s?.priority ? `priority ${s.priority}` : null,
    b.discovery === "hiring" ? "actively hiring (+)" : null,
    b.icp_fit !== "good" ? `ICP ${b.icp_fit} (−)` : null,
    s?.pain_score != null ? `pain ${s.pain_score.toFixed(0)}` : null,
    s?.business_value_score != null ? `value ${s.business_value_score.toFixed(0)}` : null,
  ].filter(Boolean).join(" · ");
  return (
    <span
      title={detail}
      className={`inline-flex items-baseline gap-1 px-2 py-0.5 rounded-md border text-xs font-bold cursor-help ${GRADE_STYLES[g.label] || GRADE_STYLES.D}`}
    >
      {g.label}
      <span className="font-normal opacity-70">{g.score}</span>
    </span>
  );
}

/** One button per channel. Email opens the full preview (HTML + send path);
 * WhatsApp and LinkedIn open the app itself with the message pre-filled or
 * copied, since neither allows programmatic sending. */
function OutreachCell({
  b,
  onPreviewEmail,
}: {
  b: Business;
  onPreviewEmail?: (b: Business) => void;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const flash = (k: string) => {
    setCopied(k);
    setTimeout(() => setCopied(null), 1400);
  };

  const waMsg = b.report?.whatsapp_message || "";
  const waNumber = (b.whatsapp || b.phone || "").replace(/[^\d+]/g, "").replace(/^\+/, "");
  const isIndia = (b.phone || "").includes("+91");
  const waHref = waNumber ? `https://wa.me/${waNumber}?text=${encodeURIComponent(waMsg)}` : null;

  const poc = (b.poc_contacts || []).find((c) => c.linkedin_url);
  const liUrl = poc?.linkedin_url || b.social_links?.linkedin || null;
  const liMsg = b.report?.whatsapp_message || b.report?.outreach_email || "";

  const btn = "px-1.5 py-0.5 rounded text-[11px] border transition-colors whitespace-nowrap";

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onPreviewEmail?.(b)}
        title="Open the full email — HTML preview, subject, call script, DM drafts"
        className={`${btn} border-indigo-500/40 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20`}
      >
        ✉️ Mail
      </button>

      {waHref ? (
        <a
          href={waHref}
          target="_blank"
          rel="noopener noreferrer"
          title={
            isIndia
              ? "Opens WhatsApp with the message pre-filled — you press send"
              : "Opens WhatsApp pre-filled. Note: many US businesses aren't on WhatsApp"
          }
          className={`${btn} border-green-500/40 bg-green-500/10 text-green-300 hover:bg-green-500/20 ${
            isIndia ? "" : "opacity-60"
          }`}
        >
          💬 WA
        </a>
      ) : (
        <span className={`${btn} border-white/10 text-slate-600`} title="No phone number">💬 —</span>
      )}

      {liUrl ? (
        <a
          href={liUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => {
            // LinkedIn allows no prefilled DM, so put the text on the
            // clipboard as the profile opens — paste is one keystroke.
            if (liMsg) navigator.clipboard.writeText(liMsg).then(() => flash("li")).catch(() => {});
          }}
          title="Opens the LinkedIn profile and copies the message (LinkedIn allows no pre-filled DMs)"
          className={`${btn} border-sky-500/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20`}
        >
          {copied === "li" ? "✓ copied" : "in DM"}
        </a>
      ) : (
        <span className={`${btn} border-white/10 text-slate-600`} title="No LinkedIn profile found">in —</span>
      )}
    </div>
  );
}

/** "I've reached out to this one." Saved immediately; optimistic so ticking
 * 20 rows in a row never feels laggy, and reverts if the save fails. */
function ContactedCell({ b }: { b: Business }) {
  const [done, setDone] = useState(!!b.contacted);
  const [saving, setSaving] = useState(false);

  const toggle = async () => {
    const next = !done;
    setDone(next);
    setSaving(true);
    try {
      await api.saveNotes(b.id, { contacted: next });
      b.contacted = next; // keep the row object in sync for re-renders
    } catch {
      setDone(!next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <input
      type="checkbox"
      checked={done}
      onChange={toggle}
      disabled={saving}
      title={done ? "Marked as contacted" : "Mark as contacted"}
      className="w-4 h-4 accent-emerald-500 cursor-pointer"
    />
  );
}

/** Free-text log — "called Tue, gatekeeper", "mailed owner", "wants a callback
 * Friday". Saves on blur so typing is never interrupted by a network call. */
function NotesCell({ b }: { b: Business }) {
  const [text, setText] = useState(b.notes || "");
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");

  const save = async () => {
    if (text === (b.notes || "")) return;
    setState("saving");
    try {
      await api.saveNotes(b.id, { notes: text });
      b.notes = text;
      setState("saved");
      setTimeout(() => setState("idle"), 1200);
    } catch {
      setState("idle");
    }
  };

  return (
    <div className="relative">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        placeholder="add note…"
        className="w-40 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
      />
      {state !== "idle" && (
        <span className="absolute -top-1.5 right-1 text-[9px] text-slate-500">
          {state === "saving" ? "…" : "✓"}
        </span>
      )}
    </div>
  );
}

function DemoCell({ url }: { url: string | null | undefined }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback((e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [url]);

  if (!url) {
    return <span className="text-slate-600 text-xs">Not yet</span>;
  }

  return (
    <div className="flex items-center gap-1.5 max-w-[160px]">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title={url}
        onClick={(e) => e.stopPropagation()}
        className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors truncate"
      >
        {url.replace(/^https?:\/\//, "")}
      </a>
      <button
        onClick={handleCopy}
        title="Copy demo link"
        className="shrink-0 text-[10px] text-slate-600 hover:text-indigo-400 transition-colors"
      >
        {copied ? "✓" : "⎘"}
      </button>
    </div>
  );
}

function PhoneCell({ value }: { value: string | null | undefined }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [value]);

  if (!value) {
    return <span className="text-slate-600 text-xs">—</span>;
  }

  return (
    <div className="flex items-center gap-1.5">
      <a
        href={`tel:${value}`}
        className="text-xs text-slate-300 hover:text-emerald-400 transition-colors font-mono"
        title="Click to call"
      >
        {value}
      </a>
      <button
        onClick={handleCopy}
        title="Copy number"
        className="text-[10px] text-slate-600 hover:text-indigo-400 transition-colors shrink-0"
      >
        {copied ? "✓" : "⎘"}
      </button>
    </div>
  );
}

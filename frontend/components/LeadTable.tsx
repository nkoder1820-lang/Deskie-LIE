"use client";

import { Business } from "@/lib/api";
import Link from "next/link";
import { useState, useCallback } from "react";

interface Props {
  businesses: Business[];
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

export default function LeadTable({ businesses }: Props) {
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
            <th className="text-left px-4 py-3 font-medium">Business</th>
            <th className="text-left px-4 py-3 font-medium">Pitch Angle</th>
            <th className="text-left px-4 py-3 font-medium hidden lg:table-cell">Email</th>
            <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Phone</th>
            <th className="text-left px-4 py-3 font-medium">Channels</th>
            <th className="text-left px-4 py-3 font-medium hidden lg:table-cell">Decision Maker</th>
            <th className="text-center px-4 py-3 font-medium">Score</th>
            <th className="text-center px-4 py-3 font-medium">Priority</th>
            <th className="text-center px-4 py-3 font-medium hidden md:table-cell">Pain</th>
            <th className="text-center px-4 py-3 font-medium hidden md:table-cell">Value</th>
            <th className="text-center px-4 py-3 font-medium hidden lg:table-cell">Digital</th>
            <th className="text-right px-4 py-3 font-medium">Reviews</th>
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
                <td className="px-4 py-3">
                  {score?.pitch_angle ? (
                    <span className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${PITCH_ANGLE_STYLES[score.pitch_angle] || "bg-white/10 text-white"}`}>
                      {score.pitch_angle}
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 hidden lg:table-cell max-w-[200px]">
                  <CopyCell value={b.email} placeholder="—" type="email" />
                </td>
                <td className="px-4 py-3 hidden md:table-cell">
                  <PhoneCell value={b.phone} />
                </td>
                <td className="px-4 py-3">
                  <ChannelIcons b={b} />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell max-w-[180px]">
                  <PocCell b={b} />
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`font-bold text-lg ${SCORE_COLOR(finalScore ?? null)}`}>
                    {finalScore != null ? finalScore.toFixed(0) : "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  {priority ? (
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PRIORITY_STYLES[priority]}`}>
                      {priority}
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-center hidden md:table-cell text-slate-300">
                  {score?.pain_score != null ? score.pain_score.toFixed(0) : "—"}
                </td>
                <td className="px-4 py-3 text-center hidden md:table-cell text-slate-300">
                  {score?.business_value_score != null ? score.business_value_score.toFixed(0) : "—"}
                </td>
                <td className="px-4 py-3 text-center hidden lg:table-cell text-slate-300">
                  {score?.digital_score != null ? score.digital_score.toFixed(0) : "—"}
                </td>
                <td className="px-4 py-3 text-right text-slate-300">
                  {b.review_count != null ? b.review_count.toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 text-right">
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
  if (b.whatsapp_link) {
    const msg = b.report?.whatsapp_message;
    links.whatsapp = msg
      ? `${b.whatsapp_link}?text=${encodeURIComponent(msg)}`
      : b.whatsapp_link;
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

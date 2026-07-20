"""
Point-of-Contact (PoC) Research Agent
======================================
Finds the actual DECISION MAKER for a business (owner, founder, GM, practice
manager, director — the person who would say yes/no to buying Deskie), not
just the generic business inbox.

Sources, in order of trust:
  1. Names/titles already scraped from the business's own site (team/about
     pages) — most accurate, rarely includes a personal email.
  2. Public Google search snippets (LinkedIn profiles, press mentions, local
     news, chamber-of-commerce listings) via SerpAPI, parsed by an LLM.
  3. Pattern-inferred email (firstname@company.com etc.) when we know the
     company domain but not a real personal email — clearly marked as
     unverified. This is the same fallback tactic paid tools use before
     verification; without a paid enrichment API (Hunter.io / Apollo.io /
     RocketReach) there is no way to get a *verified* personal email for
     free at scale.

Output:
{
  "poc_contacts": [
    {
      "name": str, "title": str,
      "emails": [str],            # real, found somewhere public
      "guessed_emails": [str],    # pattern-inferred, unverified
      "phones": [str],
      "linkedin_url": str | None,
      "confidence": "verified_on_site" | "public_search" | "inferred",
      "source": str,               # short human-readable provenance note
    }, ...
  ],
  "evidence": [str],
  "serpapi_used": bool,
}
"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.agents.nvidia_client import call_nvidia

logger = logging.getLogger(__name__)

MAX_POCS = 4
GUESS_LOCAL_BLOCKLIST = ("info", "contact", "hello", "office", "admin", "care",
                         "support", "booking", "enquiry", "reception", "team")


class PocResearchAgent:

    def run(
        self,
        business_name: str,
        city: str,
        website: Optional[str] = None,
        known_decision_makers: Optional[list[dict]] = None,
        known_business_phone: Optional[str] = None,
    ) -> dict:
        known_decision_makers = known_decision_makers or []
        domain = self._domain_from_website(website)

        raw_snippets: list[str] = []
        serpapi_used = False

        if settings.SERPAPI_KEY:
            serpapi_used = True
            linkedin_results = self._search_serpapi(
                f'"{business_name}" {city} (owner OR founder OR "general manager" OR '
                f'"managing director" OR "practice manager" OR director) site:linkedin.com/in'
            )
            web_results = self._search_serpapi(
                f'"{business_name}" {city} (owner OR founder OR manager) (email OR contact OR phone)'
            )
            raw_snippets = self._extract_snippets(linkedin_results) + self._extract_snippets(web_results)
        else:
            logger.warning("[PocAgent] SERPAPI_KEY not set — using only on-site decision makers")

        people = self._llm_extract_people(business_name, city, domain, known_decision_makers, raw_snippets)

        poc_contacts = self._merge_and_rank(known_decision_makers, people, domain)

        return {
            "poc_contacts": poc_contacts[:MAX_POCS],
            "evidence": raw_snippets[:10],
            "serpapi_used": serpapi_used,
        }

    # ── search ──────────────────────────────────────────────────────────────
    def _search_serpapi(self, query: str) -> dict:
        try:
            resp = httpx.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": settings.SERPAPI_KEY, "engine": "google", "num": 10},
                timeout=12.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[PocAgent] SerpAPI search failed for {query!r}: {e}")
            return {}

    def _extract_snippets(self, results: dict) -> list[str]:
        out = []
        for r in (results or {}).get("organic_results", [])[:8]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            link = r.get("link", "")
            out.append(f"- {title} | {snippet} | {link}")
        return out

    # ── LLM extraction ─────────────────────────────────────────────────────
    def _llm_extract_people(
        self, business_name: str, city: str, domain: Optional[str],
        known_decision_makers: list[dict], snippets: list[str],
    ) -> list[dict]:
        if not snippets:
            return []

        system = """You are a B2B sales research analyst. You are given raw Google search snippets about ONE specific business. Identify up to 4 real individuals who could be the DECISION MAKER for buying software for this business (owner, founder, general manager, practice manager, director, partner — the person who says yes/no to a purchase).

Rules:
- Only include people clearly associated with THIS business, not competitors or unrelated people who share a name.
- Only report an email, phone, or LinkedIn URL if it is LITERALLY present in the snippet text. Never invent one.
- If a LinkedIn profile URL is present, copy it exactly.
- Rank highest-authority person first (owner/founder before manager/director).
Return ONLY valid JSON:
{
  "people": [
    {"name": "<full name>", "title": "<role>", "email": "<email or null>", "phone": "<phone or null>", "linkedin_url": "<url or null>"}
  ]
}
If nothing found, return {"people": []}. Return ONLY the JSON."""

        known_text = "\n".join(f"- {d.get('name')} ({d.get('title')})" for d in known_decision_makers) or "(none)"
        user = (
            f"Business: {business_name}\nCity: {city}\nWebsite domain: {domain or 'unknown'}\n\n"
            f"Already known from the business's own website:\n{known_text}\n\n"
            f"Google search snippets:\n" + "\n".join(snippets)
        )

        result = call_nvidia(system, user, max_tokens=768, temperature=0.1)
        people = result.get("people", []) if result else []
        return [p for p in people if isinstance(p, dict) and p.get("name")]

    # ── merge + confidence + email inference ───────────────────────────────
    def _merge_and_rank(
        self, known_decision_makers: list[dict], searched_people: list[dict], domain: Optional[str],
    ) -> list[dict]:
        merged: dict[str, dict] = {}

        for d in known_decision_makers:
            name = str(d.get("name", "")).strip()
            if not name:
                continue
            merged[name.lower()] = {
                "name": name,
                "title": d.get("title") or "Team member",
                "emails": [],
                "guessed_emails": [],
                "phones": [],
                "linkedin_url": None,
                "confidence": "verified_on_site",
                "source": "Listed on the business's own website",
            }

        for p in searched_people:
            name = str(p.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            entry = merged.get(key) or {
                "name": name,
                "title": p.get("title") or "Decision maker",
                "emails": [],
                "guessed_emails": [],
                "phones": [],
                "linkedin_url": None,
                "confidence": "public_search",
                "source": "Found via public web/LinkedIn search",
            }
            if p.get("email") and p["email"] not in entry["emails"]:
                entry["emails"].append(p["email"])
                if entry["confidence"] == "verified_on_site":
                    entry["source"] += "; email found via public search"
            if p.get("phone") and p["phone"] not in entry["phones"]:
                entry["phones"].append(p["phone"])
            if p.get("linkedin_url") and not entry["linkedin_url"]:
                entry["linkedin_url"] = p["linkedin_url"]
            # Prefer a real title from search if the site only said "Team member"
            if entry["title"] == "Team member" and p.get("title"):
                entry["title"] = p["title"]
            merged[key] = entry

        people = list(merged.values())

        # Pattern-inferred emails for anyone still without a real one
        if domain:
            for entry in people:
                if entry["emails"]:
                    continue
                parts = entry["name"].split()
                if len(parts) < 2:
                    continue
                first, last = parts[0].lower(), parts[-1].lower()
                first = re.sub(r"[^a-z]", "", first)
                last = re.sub(r"[^a-z]", "", last)
                if not first or not last or first in GUESS_LOCAL_BLOCKLIST:
                    continue
                entry["guessed_emails"] = [
                    f"{first}.{last}@{domain}",
                    f"{first}@{domain}",
                ]
                if entry["confidence"] != "verified_on_site":
                    entry["confidence"] = "inferred"
                    entry["source"] = f"Name found publicly; email pattern-inferred from {domain} (unverified)"

        # Rank primarily by DECISION AUTHORITY (owner outranks GM outranks
        # manager) — this list is "who can say yes to buying", not "who's
        # easiest to reach". Contactability only breaks ties within a tier.
        def authority_tier(title: str) -> int:
            low = title.lower()
            if any(k in low for k in ("owner", "founder", "proprietor", "ceo", "president", "partner")):
                return 0
            if any(k in low for k in ("general manager", "managing director", "director", "principal")):
                return 1
            if any(k in low for k in ("manager", "chef")):
                return 2
            return 3

        def contact_score(e: dict) -> int:
            has_email = bool(e["emails"])
            return (
                0 if (has_email and e["confidence"] in ("verified_on_site", "public_search")) else
                1 if e["linkedin_url"] else
                2 if e["phones"] else
                3
            )

        people.sort(key=lambda e: (authority_tier(e["title"]), contact_score(e)))
        return people

    # ── helpers ─────────────────────────────────────────────────────────────
    def _domain_from_website(self, website: Optional[str]) -> Optional[str]:
        if not website:
            return None
        try:
            netloc = urlparse(website).netloc.lower()
            return netloc.removeprefix("www.") or None
        except Exception:
            return None

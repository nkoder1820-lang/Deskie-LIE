"""
Hiring-First Discovery Agent
============================
Inverts the classic pipeline: instead of "find businesses, then check if
they're hiring", start from live job postings for receptionist/front-desk
roles and work back to the business behind each one.

Sources: SerpAPI's google_jobs engine. Google Jobs aggregates LinkedIn,
Indeed, ZipRecruiter, Glassdoor and company career pages, and every result
carries where it was posted ("via LinkedIn") plus the real posting link —
so LinkedIn postings are captured legitimately (scraping LinkedIn itself is
ToS-prohibited and auth-walled).

Each posting's company is resolved to a real business through Google Places
(phone, website, rating, hours), and the hiring evidence is handed to the
orchestrator as a pre-seeded lead_enricher result — these leads skip the
enricher's own 2 SerpAPI verification searches, so hiring-first actually
costs LESS quota per lead than classic discovery.

Quota: 1 SerpAPI credit per ~10 postings (one google_jobs page), plus one
Google Places text search per unique company.
"""
import logging

import httpx

from app.config import settings
from app.agents.discovery_agent import BusinessDiscoveryAgent, BusinessDiscovery

logger = logging.getLogger(__name__)

_RECEPTION_KEYWORDS = (
    "reception", "front desk", "front-desk", "front office",
    "office assistant", "office coordinator", "patient coordinator",
)


class HiringDiscoveryAgent:
    def __init__(self):
        self.places = BusinessDiscoveryAgent()
        self.client = httpx.Client(timeout=20.0)
        self._last_search_error: str | None = None

    def run(
        self,
        city: str,
        role: str = "receptionist",
        industry: str | None = None,
        country: str | None = None,
        max_results: int = 20,
    ) -> list[tuple[BusinessDiscovery, dict]]:
        """Returns (business, seeded_enricher_result) pairs, newest-posting first."""
        if not settings.SERPAPI_KEY:
            logger.warning("[HiringDiscovery] SERPAPI_KEY not set — hiring-first search unavailable.")
            return []

        location = f"{city}, {country}" if country else city
        query = f"{role} {industry}".strip() if industry else role
        # ~10 postings per SerpAPI page; companies often post several roles,
        # so fetch a little deeper than max_results to fill the quota.
        max_pages = max(1, min(20, (max_results + 9) // 10 + 1))
        postings = self._search_jobs(query, location, max_pages)
        logger.info(f"[HiringDiscovery] {len(postings)} postings for '{query}' in {location}")
        if not postings and self._last_search_error:
            # Surface the real reason in the job status instead of silently
            # "completing" with 0 leads — a 429 means the SerpAPI monthly
            # quota is exhausted.
            hint = " — SerpAPI monthly quota exhausted" if "429" in self._last_search_error else ""
            raise RuntimeError(f"Job-posting search failed: {self._last_search_error}{hint}")

        # A company may run several postings — group them so each business
        # becomes ONE lead carrying all its hiring evidence.
        by_company: dict[str, list[dict]] = {}
        for p in postings:
            name = (p.get("company_name") or "").strip()
            if name:
                by_company.setdefault(name, []).append(p)

        results: list[tuple[BusinessDiscovery, dict]] = []
        for company, jobs in by_company.items():
            if len(results) >= max_results:
                break
            biz = self._resolve_company(company, city, industry, country)
            if not biz:
                logger.info(f"[HiringDiscovery] Could not resolve '{company}' via Places — skipped.")
                continue
            results.append((biz, self._seed_enricher(role, jobs)))
        logger.info(f"[HiringDiscovery] Resolved {len(results)} hiring businesses.")
        return results

    # ── Google Jobs search (via SerpAPI) ────────────────────────────────────
    def _search_jobs(self, query: str, location: str, max_pages: int) -> list[dict]:
        postings: list[dict] = []
        token = None
        for _ in range(max_pages):
            params = {
                "engine": "google_jobs",
                "q": query,
                "location": location,
                "api_key": settings.SERPAPI_KEY,
            }
            if token:
                params["next_page_token"] = token
            try:
                r = self.client.get("https://serpapi.com/search", params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                logger.error(f"[HiringDiscovery] google_jobs search failed: {e}")
                self._last_search_error = str(e)[:200]
                break
            jobs = data.get("jobs_results") or []
            postings.extend(jobs)
            token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not jobs or not token:
                break
        return postings

    # ── Company → real business (Google Places) ─────────────────────────────
    def _resolve_company(
        self, company: str, city: str, industry: str | None, country: str | None
    ) -> BusinessDiscovery | None:
        if not self.places.api_key:
            logger.warning("[HiringDiscovery] No Google Places key — cannot resolve companies.")
            return None
        location = f"{city}, {country}" if country else city
        category = industry or "hiring_leads"
        try:
            found = self.places._search_places(f"{company} {location}", 1, category, city, set())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HiringDiscovery] Places lookup failed for '{company}': {e}")
            return None
        if not found:
            return None
        biz = found[0]
        biz.source = "google_jobs"
        return biz

    # ── Pre-seeded lead_enricher result ─────────────────────────────────────
    def _seed_enricher(self, role: str, jobs: list[dict]) -> dict:
        """Same shape the LeadEnricherAgent returns, built from the postings we
        already hold — the orchestrator skips its own SerpAPI verification."""
        evidence: list[str] = []
        sources: list[dict] = []
        reception_hit = any(k in role.lower() for k in _RECEPTION_KEYWORDS)
        for j in jobs[:5]:
            title = (j.get("title") or "Job posting").strip()
            via = (j.get("via") or "").removeprefix("via ").strip()
            evidence.append(f"{title}" + (f" (posted on {via})" if via else ""))
            if any(k in title.lower() for k in _RECEPTION_KEYWORDS):
                reception_hit = True
            url = j.get("share_link") or j.get("link")
            if not url:
                for opt in j.get("apply_options") or []:
                    if opt.get("link"):
                        url = opt["link"]
                        break
            if url:
                company = (j.get("company_name") or "").strip()
                sources.append({"title": f"{title} — {company}"[:120], "url": url})
        return {
            "is_hiring_receptionist": reception_hit,
            "is_hiring_any": True,
            "hiring_evidence": evidence,
            "hiring_sources": sources[:3],
            "runs_google_ads": False,
            "ads_evidence": [],
            "ads_sources": [],
            "seeded_from": "google_jobs",
        }

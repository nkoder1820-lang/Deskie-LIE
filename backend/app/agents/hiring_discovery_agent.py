"""
Hiring-First Discovery Agent
============================
Inverts the classic pipeline: instead of "find businesses, then check if
they're hiring", start from live job postings for receptionist/front-desk
roles and work back to the business behind each one.

Providers, in order:
1. Adzuna (free official jobs API, developer.adzuna.com) — aggregates the
   major job boards; effectively unlimited for this tool's scale.
2. SerpAPI google_jobs (fallback) — Google Jobs aggregation incl. LinkedIn
   ("via LinkedIn" + real posting link). ~1 credit per ~10 postings.
Scraping LinkedIn directly is ToS-prohibited and auth-walled; both providers
surface the same postings legitimately, source link included.

Each posting's company is resolved to a real business through Google Places
(phone, website, rating, hours) and marked source="adzuna_jobs"/"google_jobs"
— the API exposes this as discovery="hiring" so hiring-first leads stay
distinguishable from classic industry-search leads. The hiring evidence is
handed to the orchestrator as a pre-seeded lead_enricher result, so these
leads never spend SerpAPI quota on re-verification.
"""
import logging
import re

import httpx

from app.config import settings
from app.agents.discovery_agent import BusinessDiscoveryAgent, BusinessDiscovery
from app.scoring.icp import is_staffing_agency

logger = logging.getLogger(__name__)

_RECEPTION_KEYWORDS = (
    "reception", "front desk", "front-desk", "front office",
    "office assistant", "office coordinator", "patient coordinator",
)

# Adzuna's API is namespaced by country path segment.
_ADZUNA_COUNTRIES = {
    "us": "us", "usa": "us", "united states": "us",
    "in": "in", "india": "in",
    "uk": "gb", "gb": "gb", "united kingdom": "gb",
    "ca": "ca", "canada": "ca",
    "au": "au", "australia": "au",
    "sg": "sg", "singapore": "sg",
    "nz": "nz", "new zealand": "nz",
    "za": "za", "south africa": "za",
    "de": "de", "germany": "de",
    "fr": "fr", "france": "fr",
    "it": "it", "italy": "it",
    "es": "es", "spain": "es",
    "nl": "nl", "netherlands": "nl",
    "at": "at", "austria": "at",
    "pl": "pl", "poland": "pl",
    "br": "br", "brazil": "br",
    "mx": "mx", "mexico": "mx",
}

_IN_CITY_HINTS = (
    "mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "chennai",
    "pune", "kolkata", "ahmedabad", "jaipur", "noida", "gurgaon", "gurugram",
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
        location = f"{city}, {country}" if country else city
        query = f"{role} {industry}".strip() if industry else role

        # Provider 1: Adzuna (free official API). Provider 2: SerpAPI fallback.
        postings: list[dict] = []
        source = "adzuna_jobs"
        if settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY:
            postings = self._search_adzuna(query, city, country, max_results)
            logger.info(f"[HiringDiscovery] Adzuna: {len(postings)} postings for '{query}' in {location}")
        if not postings and settings.SERPAPI_KEY:
            source = "google_jobs"
            max_pages = max(1, min(20, (max_results + 9) // 10 + 1))
            postings = self._search_serpapi_jobs(query, location, max_pages)
            logger.info(f"[HiringDiscovery] google_jobs: {len(postings)} postings for '{query}' in {location}")
        if not postings:
            if self._last_search_error:
                # Surface the real reason in the job status instead of silently
                # "completing" with 0 leads — a 429 means a quota is exhausted.
                hint = " — provider quota exhausted" if "429" in self._last_search_error else ""
                raise RuntimeError(f"Job-posting search failed: {self._last_search_error}{hint}")
            logger.warning("[HiringDiscovery] No postings found (and no provider errors).")
            return []

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
            # ICP gate: staffing/recruiting agencies post most receptionist
            # ads, but the role isn't at their own front desk — pure noise.
            # Hard-skip before spending a Places call on them.
            if is_staffing_agency(company):
                logger.info(f"[HiringDiscovery] '{company}' looks like a staffing agency — gated out.")
                continue
            biz = self._resolve_company(company, city, industry, country, source)
            if not biz:
                logger.info(f"[HiringDiscovery] Could not resolve '{company}' via Places — skipped.")
                continue
            results.append((biz, self._seed_enricher(role, jobs)))
        logger.info(f"[HiringDiscovery] Resolved {len(results)} hiring businesses.")
        return results

    # ── Adzuna search (free official API) ───────────────────────────────────
    def _adzuna_country(self, country: str | None, city: str) -> str:
        code = _ADZUNA_COUNTRIES.get((country or "").strip().lower())
        if code:
            return code
        if any(c in city.lower() for c in _IN_CITY_HINTS):
            return "in"
        return "us"

    def _search_adzuna(self, query: str, city: str, country: str | None,
                       max_results: int) -> list[dict]:
        cc = self._adzuna_country(country, city)
        # Companies repeat across postings — fetch deeper than max_results.
        want = min(max(max_results * 3, 50), 250)
        postings: list[dict] = []
        page = 1
        while len(postings) < want and page <= 5:
            try:
                r = self.client.get(
                    f"https://api.adzuna.com/v1/api/jobs/{cc}/search/{page}",
                    params={
                        "app_id": settings.ADZUNA_APP_ID,
                        "app_key": settings.ADZUNA_APP_KEY,
                        "what": query,
                        "where": city,
                        "results_per_page": 50,
                    },
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                logger.error(f"[HiringDiscovery] Adzuna search failed: {e}")
                self._last_search_error = f"Adzuna: {str(e)[:180]}"
                break
            results = data.get("results") or []
            for j in results:
                postings.append({
                    "company_name": ((j.get("company") or {}).get("display_name") or "").strip(),
                    "title": re.sub(r"<[^>]+>", "", j.get("title") or "Job posting").strip(),
                    "via": "Adzuna",
                    "url": j.get("redirect_url"),
                })
            if len(results) < 50:
                break
            page += 1
        return postings

    # ── Google Jobs search (via SerpAPI, fallback provider) ─────────────────
    def _search_serpapi_jobs(self, query: str, location: str, max_pages: int) -> list[dict]:
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
            for j in jobs:
                url = j.get("share_link") or j.get("link")
                if not url:
                    for opt in j.get("apply_options") or []:
                        if opt.get("link"):
                            url = opt["link"]
                            break
                postings.append({
                    "company_name": (j.get("company_name") or "").strip(),
                    "title": (j.get("title") or "Job posting").strip(),
                    "via": (j.get("via") or "").removeprefix("via ").strip() or "Google Jobs",
                    "url": url,
                })
            token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not jobs or not token:
                break
        return postings

    # ── Company → real business (Google Places) ─────────────────────────────
    def _resolve_company(
        self, company: str, city: str, industry: str | None, country: str | None,
        source: str = "google_jobs",
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
        biz.source = source
        return biz

    # ── Pre-seeded lead_enricher result ─────────────────────────────────────
    def _seed_enricher(self, role: str, jobs: list[dict]) -> dict:
        """Same shape the LeadEnricherAgent returns, built from the (normalized)
        postings we already hold — the orchestrator skips SerpAPI verification."""
        evidence: list[str] = []
        sources: list[dict] = []
        reception_hit = any(k in role.lower() for k in _RECEPTION_KEYWORDS)
        for j in jobs[:5]:
            title = j["title"]
            via = j["via"]
            evidence.append(f"{title}" + (f" (posted on {via})" if via else ""))
            if any(k in title.lower() for k in _RECEPTION_KEYWORDS):
                reception_hit = True
            if j.get("url"):
                sources.append({"title": f"{title} — {j['company_name']}"[:120], "url": j["url"]})
        return {
            "is_hiring_receptionist": reception_hit,
            "is_hiring_any": True,
            "hiring_evidence": evidence,
            "hiring_sources": sources[:3],
            "runs_google_ads": False,
            "ads_evidence": [],
            "ads_sources": [],
            "seeded_from": "job_postings",
        }
